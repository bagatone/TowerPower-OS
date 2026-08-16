from __future__ import annotations

from io import StringIO
from pathlib import Path
import re

from alembic import command
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy.exc import DBAPIError

from src.tpo_core.infrastructure.postgresql.alembic import make_config
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    _insert_valid_planning_graph,
    isolated_postgresql as migration_postgresql,
)

ROOT = Path(__file__).parents[3]
MIGRATION = ROOT / "migrations/versions/20260812_0009_delivery_fulfilment_schema.py"


@pytest.fixture(scope="module")
def delivery_postgresql_engine(migration_postgresql):
    """Prepare 0009 once, while keeping lifecycle tests on their own connection."""
    connection = migration_postgresql
    if connection.in_transaction():
        connection.rollback()
    command.upgrade(make_config(connection=connection), "20260812_0009")
    connection.commit()
    yield connection.engine
    if connection.in_transaction():
        connection.rollback()


@pytest.fixture
def isolated_postgresql(delivery_postgresql_engine):
    """Give every behavioral test a fresh connection and rollback-only scope."""
    with delivery_postgresql_engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            if transaction.is_active:
                transaction.rollback()
            elif connection.in_transaction():
                connection.rollback()
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
            connection.rollback()


def _ddl() -> str:
    output = StringIO()
    config = make_config()
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@invalid/tpo")
    config.output_buffer = output
    command.upgrade(config, "20260811_0008:20260812_0009", sql=True)
    return re.sub(r"\s+", " ", output.getvalue()).strip()


def test_delivery_revision_is_single_head_after_0008() -> None:
    script = ScriptDirectory.from_config(make_config())
    assert script.get_heads() == ["20260815_0013"]
    revision = script.get_revision("20260812_0009")
    assert revision is not None
    assert revision.down_revision == "20260811_0008"


def test_delivery_offline_ddl_contains_frozen_contract() -> None:
    ddl = _ddl()
    for fragment in (
        "CREATE TABLE tpo.consegne_ordini",
        "CREATE TABLE tpo.righe_consegna",
        "NUMERIC(20, 6) NOT NULL",
        "CONSTRAINT uq_righe_ordine_fulfilment_key UNIQUE",
        "CONSTRAINT fk_righe_consegna_riga_ordine FOREIGN KEY",
        "ADD COLUMN riga_consegna_id BIGINT",
        "CREATE FUNCTION tpo.fn_consegne_ordini_cliente_coerente() RETURNS trigger LANGUAGE plpgsql",
        "CREATE CONSTRAINT TRIGGER ct_consegne_ordini_cliente_coerente",
        "DEFERRABLE INITIALLY DEFERRED",
        "historical delivery fulfilment commissioning required",
        "origine_tipo = 'CONSEGNA' AND consegna_id IS NOT NULL AND riga_consegna_id IS NOT NULL",
    ):
        assert fragment in ddl


def test_delivery_migration_has_no_business_dml() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for statement in ("INSERT INTO", "UPDATE tpo.", "DELETE FROM"):
        assert statement not in source
    assert "id_sequences" not in source
    ddl = _ddl()
    assert "INSERT INTO" not in ddl
    assert "DELETE FROM" not in ddl
    assert not re.search(r"\bUPDATE\s+tpo\.", ddl, re.IGNORECASE)


def _seed(connection, number: int = 880001):
    assert connection.exec_driver_sql("SELECT to_regclass('tpo.clienti')").scalar_one() == "tpo.clienti"
    client_a = connection.exec_driver_sql(f"""
      INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
      VALUES ('CLI-{number:06d}','Delivery client A','test-suite',CURRENT_TIMESTAMP,'test-suite') RETURNING id
    """).scalar_one()
    client_b = connection.exec_driver_sql(f"""
      INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
      VALUES ('CLI-{number + 1:06d}','Delivery client B','test-suite',CURRENT_TIMESTAMP,'test-suite') RETURNING id
    """).scalar_one()
    variety = connection.exec_driver_sql(f"""
      INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,updated_at,updated_by)
      VALUES ('VAR-{number:06d}','Delivery variety','ATTIVA','test-suite',CURRENT_TIMESTAMP,'test-suite') RETURNING id
    """).scalar_one()
    order = connection.exec_driver_sql(f"""
      INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,created_by)
      VALUES ('ORD-{number:06d}',{client_a},CURRENT_DATE,CURRENT_DATE,'APERTO','MANUALE','test-suite') RETURNING id
    """).scalar_one()
    line = connection.exec_driver_sql(f"""
      INSERT INTO tpo.righe_ordine(ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
      VALUES ({order},1,{variety},1,'SET','RO-{number:06d}') RETURNING id
    """).scalar_one()
    delivery = connection.exec_driver_sql(f"""
      INSERT INTO tpo.consegne(public_id,cliente_id,stato,data_prevista,created_by)
      VALUES ('CON-{number:06d}',{client_a},'PROGRAMMATA',CURRENT_DATE,'test-suite') RETURNING id
    """).scalar_one()
    _checkpoint(connection)
    return client_a, client_b, variety, order, line, delivery


def _historical_delivery(connection, number: int, state: str) -> tuple[int, int]:
    client = connection.exec_driver_sql(f"""
      INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
      VALUES ('CLI-{number:06d}','Historical gate client','test-suite',CURRENT_TIMESTAMP,'test-suite') RETURNING id
    """).scalar_one()
    effective = "CURRENT_TIMESTAMP" if state == "CONSEGNATA" else "NULL"
    delivery = connection.exec_driver_sql(f"""
      INSERT INTO tpo.consegne(public_id,cliente_id,stato,data_prevista,data_effettiva,created_by)
      VALUES ('CON-{number:06d}',{client},'{state}',CURRENT_DATE,{effective},'test-suite') RETURNING id
    """).scalar_one()
    connection.commit()
    return client, delivery


def _force_constraints(connection) -> None:
    connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")


def _checkpoint(connection) -> None:
    _force_constraints(connection)
    connection.exec_driver_sql("SET CONSTRAINTS ALL DEFERRED")


def _assert_connection_healthy(connection) -> None:
    assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1


def _expect_db_failure(connection, marker: str, action) -> None:
    savepoint = connection.begin_nested()
    try:
        with pytest.raises(DBAPIError, match=marker):
            action()
            _force_constraints(connection)
    finally:
        savepoint.rollback()
    _assert_connection_healthy(connection)


def _link_order(connection, delivery: int, order: int, position: int = 1) -> None:
    connection.exec_driver_sql(
        f"INSERT INTO tpo.consegne_ordini(consegna_id,ordine_id,posizione) VALUES ({delivery},{order},{position})"
    )


def _delivery_line(
    connection, delivery: int, order: int, line: int, position: int,
    variety: int, quantity: str, uom: str = "SET", correction: int | None = None,
) -> int:
    correction_sql = "NULL" if correction is None else str(correction)
    return connection.exec_driver_sql(f"""
      INSERT INTO tpo.righe_consegna(
        consegna_id,ordine_id,riga_ordine_id,posizione,varieta_id,quantita,
        unita_misura,rettifica_riga_consegna_id,created_at,created_by
      ) VALUES (
        {delivery},{order},{line},{position},{variety},{quantity},'{uom}',
        {correction_sql},CURRENT_TIMESTAMP,'test-suite'
      ) RETURNING id
    """).scalar_one()


def _new_delivery(connection, number: int, client: int, state: str = "PROGRAMMATA") -> int:
    return connection.exec_driver_sql(f"""
      INSERT INTO tpo.consegne(public_id,cliente_id,stato,data_prevista,created_by)
      VALUES ('CON-{number:06d}',{client},'{state}',CURRENT_DATE,'test-suite') RETURNING id
    """).scalar_one()


def _make_effective(connection, delivery: int, order: int, order_state: str) -> None:
    connection.exec_driver_sql(f"UPDATE tpo.ordini SET stato='{order_state}' WHERE id={order}")
    connection.exec_driver_sql(
        f"UPDATE tpo.consegne SET stato='CONSEGNATA',data_effettiva=CURRENT_TIMESTAMP WHERE id={delivery}"
    )
    _checkpoint(connection)


def _prepare_delivery(connection, delivery: int, order: int, line: int, variety: int, quantity: str) -> int:
    _link_order(connection, delivery, order)
    return _delivery_line(connection, delivery, order, line, 1, variety, quantity)


def _delete_historical(connection, client: int, delivery: int) -> None:
    connection.exec_driver_sql(f"DELETE FROM tpo.consegne WHERE id={delivery}")
    connection.exec_driver_sql(f"DELETE FROM tpo.clienti WHERE id={client}")
    connection.commit()


def _movement(
    connection, public_id: str, variety: int, origin: str, *,
    delivery: int | None = None, delivery_line: int | None = None,
    harvest: int | None = None,
) -> None:
    connection.exec_driver_sql(
        """
        INSERT INTO tpo.movimenti_magazzino(
          public_id,varieta_id,unita_misura,tipo,direzione,quantita,
          data_movimento,motivo,origine_tipo,raccolta_id,consegna_id,
          riga_consegna_id,created_by
        ) VALUES (%s,%s,'SET','RETTIFICA','POSITIVO',1,CURRENT_TIMESTAMP,
                  'test-only',%s,%s,%s,%s,'test-suite')
        """,
        (public_id, variety, origin, harvest, delivery, delivery_line),
    )


def _real_harvest(connection) -> tuple[int, int]:
    _, _, variety = _insert_valid_planning_graph(connection)
    cultivar = connection.exec_driver_sql(
        "SELECT id FROM tpo.cultivar WHERE varieta_id=%s", (variety,)
    ).scalar_one()
    cultivar_use = connection.exec_driver_sql(
        "SELECT id FROM tpo.cultivar_usi WHERE cultivar_id=%s", (cultivar,)
    ).scalar_one()
    protocol_version = connection.exec_driver_sql("""
      SELECT pv.id FROM tpo.protocollo_versioni pv
      JOIN tpo.protocolli p ON p.id=pv.protocollo_id
      WHERE p.cultivar_uso_id=%s
    """, (cultivar_use,)).scalar_one()
    seed = connection.exec_driver_sql("""
      INSERT INTO tpo.sementi(
        fornitore,referenza_commerciale,created_by,updated_at,updated_by
      ) VALUES ('test-only supplier','test-only seed','test-suite',
                CURRENT_TIMESTAMP,'test-suite') RETURNING id
    """).scalar_one()
    lot = connection.exec_driver_sql("""
      INSERT INTO tpo.lotti_seme(
        semente_id,numero_lotto_produttore,data_ricezione,quantita_iniziale,
        quantita_residua,unita_misura,created_by,updated_at,updated_by
      ) VALUES (%s,'test-only-lot',CURRENT_DATE,10,9,'GRAM','test-suite',
                CURRENT_TIMESTAMP,'test-suite') RETURNING id
    """, (seed,)).scalar_one()
    sowing = connection.exec_driver_sql("""
      INSERT INTO tpo.semine(
        public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,
        protocollo_versione_id,stato,quantita_seme,unita_misura,data_avvio,
        causa_origine,cultivar_snapshot,uso_produttivo_snapshot,
        lotto_seme_snapshot,protocollo_snapshot,created_by
      ) VALUES ('SEM-990001',%s,%s,%s,%s,%s,'AVVIATA',1,'GRAM',
                CURRENT_TIMESTAMP,'test-only','test-only','test-only',
                'test-only','test-only','test-suite') RETURNING id
    """, (variety, cultivar, cultivar_use, lot, protocol_version)).scalar_one()
    harvest = connection.exec_driver_sql("""
      INSERT INTO tpo.raccolte(
        public_id,semina_id,data_raccolta,quantita,unita_misura,created_by
      ) VALUES ('RAC-990001',%s,CURRENT_TIMESTAMP,1,'SET','test-suite')
      RETURNING id
    """, (sowing,)).scalar_one()
    return variety, harvest


def test_historical_gate_no_delivery_clean_cycle(migration_postgresql) -> None:
    connection = migration_postgresql
    config = make_config(connection=connection)
    command.upgrade(config, "20260811_0008")
    command.upgrade(config, "20260812_0009")
    command.downgrade(config, "20260811_0008")
    command.upgrade(config, "20260812_0009")
    command.downgrade(config, "20260811_0008")


@pytest.mark.parametrize(
    ("number", "state"),
    ((870001, "PROGRAMMATA"), (870002, "IN_PREPARAZIONE"), (870003, "ANNULLATA")),
    ids=("programmata", "in_preparazione", "annullata"),
)
def test_historical_gate_non_effective_delivery_passes(migration_postgresql, number, state) -> None:
    connection = migration_postgresql
    config = make_config(connection=connection)
    command.upgrade(config, "20260811_0008")
    client, delivery = _historical_delivery(connection, number, state)
    command.upgrade(config, "20260812_0009")
    assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260812_0009"
    command.downgrade(config, "20260811_0008")
    _delete_historical(connection, client, delivery)


def test_historical_gate_effective_delivery_fails_closed(migration_postgresql) -> None:
    connection = migration_postgresql
    config = make_config(connection=connection)
    command.upgrade(config, "20260811_0008")
    client, delivery = _historical_delivery(connection, 870010, "CONSEGNATA")
    with pytest.raises(RuntimeError, match="historical delivery fulfilment commissioning required"):
        command.upgrade(config, "20260812_0009")
    connection.rollback()
    assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260811_0008"
    assert connection.exec_driver_sql("SELECT to_regclass('tpo.righe_consegna')").scalar_one() is None
    assert connection.exec_driver_sql(f"SELECT stato::text FROM tpo.consegne WHERE id={delivery}").scalar_one() == "CONSEGNATA"
    _delete_historical(connection, client, delivery)
    command.upgrade(config, "20260812_0009")
    connection.commit()


def test_real_postgresql_upgrade_catalog_behavior_downgrade_reupgrade(migration_postgresql) -> None:
    connection = migration_postgresql
    config = make_config(connection=connection)
    command.upgrade(config, "20260812_0009")
    assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260812_0009"
    assert connection.exec_driver_sql("SELECT to_regclass('tpo.consegne_ordini')").scalar_one() == "tpo.consegne_ordini"
    assert connection.exec_driver_sql("SELECT to_regclass('tpo.righe_consegna')").scalar_one() == "tpo.righe_consegna"
    functions = set(connection.exec_driver_sql("""
      SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      WHERE n.nspname='tpo' AND p.proname LIKE 'fn_%%cliente_coerente%%'
    """).scalars())
    assert functions == {
        "fn_consegne_ordini_cliente_coerente",
        "fn_consegne_cliente_coerente_ordini",
        "fn_ordini_cliente_coerente_consegne",
    }
    deferred = connection.exec_driver_sql("""
      SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
      JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='tpo' AND t.tgname LIKE 'ct_%%' AND t.tgdeferrable AND t.tginitdeferred
        AND t.tgname IN ('ct_consegne_ordini_cliente_coerente','ct_consegne_cliente_coerente_ordini','ct_ordini_cliente_coerente_consegne')
    """).scalar_one()
    assert deferred == 3
    connection.commit()



def test_client_consistency_same_client_join_passes(isolated_postgresql) -> None:
    connection = isolated_postgresql
    client, _, _, order, _, delivery = _seed(connection, 875001)
    _link_order(connection, delivery, order)
    _checkpoint(connection)
    assert connection.exec_driver_sql(f"SELECT cliente_id FROM tpo.ordini WHERE id={order}").scalar_one() == client


def test_client_consistency_join_mismatch_fails(isolated_postgresql) -> None:
    connection = isolated_postgresql
    _, client_b, _, _, _, delivery = _seed(connection, 875010)
    other_order = connection.exec_driver_sql(f"""
      INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,created_by)
      VALUES ('ORD-875012',{client_b},CURRENT_DATE,CURRENT_DATE,'APERTO','MANUALE','test-suite') RETURNING id
    """).scalar_one()
    _checkpoint(connection)
    _expect_db_failure(connection, "ct_consegne_ordini_cliente_coerente", lambda: _link_order(connection, delivery, other_order))
    connection.rollback()


@pytest.mark.parametrize("parent", ("consegna", "ordine"))
def test_client_consistency_parent_update_fails(isolated_postgresql, parent) -> None:
    connection = isolated_postgresql
    number = 875020 if parent == "consegna" else 875030
    _, client_b, _, order, _, delivery = _seed(connection, number)
    _link_order(connection, delivery, order)
    _checkpoint(connection)
    if parent == "consegna":
        marker = "ct_consegne_cliente_coerente_ordini"
        action = lambda: connection.exec_driver_sql(f"UPDATE tpo.consegne SET cliente_id={client_b} WHERE id={delivery}")
    else:
        marker = "ct_ordini_cliente_coerente_consegne"
        action = lambda: connection.exec_driver_sql(f"UPDATE tpo.ordini SET cliente_id={client_b} WHERE id={order}")
    _expect_db_failure(connection, marker, action)
    connection.rollback()


def test_real_postgresql_client_join_mismatch_and_partial_overdelivery(isolated_postgresql) -> None:
    connection = isolated_postgresql
    _, client_b, variety, order, line, delivery = _seed(connection)
    other_order = connection.exec_driver_sql(f"""
      INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,created_by)
      VALUES ('ORD-880002',{client_b},CURRENT_DATE,CURRENT_DATE,'APERTO','MANUALE','test-suite') RETURNING id
    """).scalar_one()
    _checkpoint(connection)
    connection.exec_driver_sql(f"INSERT INTO tpo.consegne_ordini VALUES ({delivery},{order},1)")
    _checkpoint(connection)
    _expect_db_failure(
        connection, "ct_consegne_cliente_coerente_ordini",
        lambda: connection.exec_driver_sql(
            f"UPDATE tpo.consegne SET cliente_id={client_b} WHERE id={delivery}"
        ),
    )
    _expect_db_failure(
        connection, "ct_ordini_cliente_coerente_consegne",
        lambda: connection.exec_driver_sql(
            f"UPDATE tpo.ordini SET cliente_id={client_b} WHERE id={order}"
        ),
    )
    _expect_db_failure(
        connection, "ct_consegne_ordini_cliente_coerente",
        lambda: connection.exec_driver_sql(
            f"INSERT INTO tpo.consegne_ordini VALUES ({delivery},{other_order},2)"
        ),
    )

    connection.exec_driver_sql(f"INSERT INTO tpo.righe_consegna(consegna_id,ordine_id,riga_ordine_id,posizione,varieta_id,quantita,unita_misura,created_at,created_by) VALUES ({delivery},{order},{line},1,{variety},0.5,'SET',CURRENT_TIMESTAMP,'test-suite')")
    connection.exec_driver_sql(f"UPDATE tpo.ordini SET stato='PARZIALMENTE_EVASO' WHERE id={order}")
    connection.exec_driver_sql(f"UPDATE tpo.consegne SET stato='CONSEGNATA',data_effettiva=CURRENT_TIMESTAMP WHERE id={delivery}")
    _checkpoint(connection)

    delivery2 = connection.exec_driver_sql(f"INSERT INTO tpo.consegne(public_id,cliente_id,stato,data_prevista,created_by) VALUES ('CON-880002',(SELECT cliente_id FROM tpo.ordini WHERE id={order}),'PROGRAMMATA',CURRENT_DATE,'test-suite') RETURNING id").scalar_one()
    connection.exec_driver_sql(f"INSERT INTO tpo.consegne_ordini VALUES ({delivery2},{order},1)")
    connection.exec_driver_sql(f"INSERT INTO tpo.righe_consegna(consegna_id,ordine_id,riga_ordine_id,posizione,varieta_id,quantita,unita_misura,created_at,created_by) VALUES ({delivery2},{order},{line},1,{variety},0.5,'SET',CURRENT_TIMESTAMP,'test-suite')")
    connection.exec_driver_sql(f"UPDATE tpo.ordini SET stato='EVASO' WHERE id={order}")
    connection.exec_driver_sql(f"UPDATE tpo.consegne SET stato='CONSEGNATA',data_effettiva=CURRENT_TIMESTAMP WHERE id={delivery2}")
    _checkpoint(connection)

    delivered = connection.exec_driver_sql(f"SELECT sum(rc.quantita) FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id WHERE rc.riga_ordine_id={line} AND c.stato='CONSEGNATA'").scalar_one()
    assert str(delivered) == "1.000000"
    delivery3 = connection.exec_driver_sql(f"INSERT INTO tpo.consegne(public_id,cliente_id,stato,data_prevista,created_by) VALUES ('CON-880003',(SELECT cliente_id FROM tpo.ordini WHERE id={order}),'PROGRAMMATA',CURRENT_DATE,'test-suite') RETURNING id").scalar_one()
    connection.exec_driver_sql(f"INSERT INTO tpo.consegne_ordini VALUES ({delivery3},{order},1)")
    connection.exec_driver_sql(f"INSERT INTO tpo.righe_consegna(consegna_id,ordine_id,riga_ordine_id,posizione,varieta_id,quantita,unita_misura,created_at,created_by) VALUES ({delivery3},{order},{line},1,{variety},0.1,'SET',CURRENT_TIMESTAMP,'test-suite')")
    connection.exec_driver_sql(f"UPDATE tpo.consegne SET stato='CONSEGNATA',data_effettiva=CURRENT_TIMESTAMP WHERE id={delivery3}")
    _expect_db_failure(
        connection, "ct_righe_consegna_fulfilment_bounds", lambda: None,
    )


@pytest.mark.parametrize(
    ("number", "quantity", "wrong_state", "expected"),
    (
        (885001, None, "PARZIALMENTE_EVASO", "expected APERTO"),
        (885010, "0.5", "EVASO", "expected PARZIALMENTE_EVASO"),
        (885020, "1.0", "APERTO", "expected EVASO"),
    ),
    ids=("zero_as_partial", "partial_as_full", "full_as_open"),
)
def test_order_state_incoherence_fails(isolated_postgresql, number, quantity, wrong_state, expected) -> None:
    connection = isolated_postgresql
    _, _, variety, order, line, delivery = _seed(connection, number)
    if quantity is None:
        _expect_db_failure(
            connection, expected,
            lambda: connection.exec_driver_sql(f"UPDATE tpo.ordini SET stato='{wrong_state}' WHERE id={order}"),
        )
    else:
        _prepare_delivery(connection, delivery, order, line, variety, quantity)
        connection.exec_driver_sql(f"UPDATE tpo.ordini SET stato='{wrong_state}' WHERE id={order}")
        connection.exec_driver_sql(f"UPDATE tpo.consegne SET stato='CONSEGNATA',data_effettiva=CURRENT_TIMESTAMP WHERE id={delivery}")
        with pytest.raises(DBAPIError, match=expected):
            _force_constraints(connection)
        connection.rollback()


@pytest.mark.parametrize(
    ("number", "variant"),
    ((886001, "line"), (886010, "variety"), (886020, "uom")),
)
def test_correction_target_dimensions_must_match(isolated_postgresql, number, variant) -> None:
    connection = isolated_postgresql
    client, _, variety, order, line, delivery = _seed(connection, number)
    _link_order(connection, delivery, order)
    original = _delivery_line(connection, delivery, order, line, 1, variety, "1")

    target_variety = variety
    target_uom = "SET"
    if variant == "variety":
        target_variety = connection.exec_driver_sql(f"""
          INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,updated_at,updated_by)
          VALUES ('VAR-{number + 1:06d}','Correction alternate variety','ATTIVA','test-suite',CURRENT_TIMESTAMP,'test-suite') RETURNING id
        """).scalar_one()
    if variant == "uom":
        target_uom = "UNIT"
    target_line = connection.exec_driver_sql(f"""
      INSERT INTO tpo.righe_ordine(ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
      VALUES ({order},2,{target_variety},1,'{target_uom}','RO-{number + 1:06d}') RETURNING id
    """).scalar_one()
    _make_effective(connection, delivery, order, "PARZIALMENTE_EVASO")
    correction_delivery = _new_delivery(connection, number + 2, client)
    _link_order(connection, correction_delivery, order)
    _delivery_line(
        connection, correction_delivery, order, target_line, 1,
        target_variety, "-0.1", target_uom, original,
    )
    with pytest.raises(DBAPIError, match="ct_righe_consegna_rettifica_coerente"):
        _force_constraints(connection)
    connection.rollback()


def test_correction_original_must_already_be_effective(isolated_postgresql) -> None:
    connection = isolated_postgresql
    client, _, variety, order, line, delivery = _seed(connection, 886030)
    _link_order(connection, delivery, order)
    original = _delivery_line(connection, delivery, order, line, 1, variety, "1")
    correction_delivery = _new_delivery(connection, 886032, client)
    _link_order(connection, correction_delivery, order)
    _delivery_line(connection, correction_delivery, order, line, 1, variety, "-0.1", "SET", original)
    with pytest.raises(DBAPIError, match="ct_righe_consegna_rettifica_coerente"):
        _force_constraints(connection)
    connection.rollback()


def test_correction_cannot_make_delivered_negative(isolated_postgresql) -> None:
    connection = isolated_postgresql
    client, _, variety, order, line, delivery = _seed(connection, 886040)
    _link_order(connection, delivery, order)
    original = _delivery_line(connection, delivery, order, line, 1, variety, "1")
    _make_effective(connection, delivery, order, "EVASO")
    correction_delivery = _new_delivery(connection, 886042, client)
    _link_order(connection, correction_delivery, order)
    _delivery_line(connection, correction_delivery, order, line, 1, variety, "-1.1", "SET", original)
    connection.exec_driver_sql(f"UPDATE tpo.ordini SET stato='APERTO' WHERE id={order}")
    connection.exec_driver_sql(f"UPDATE tpo.consegne SET stato='CONSEGNATA',data_effettiva=CURRENT_TIMESTAMP WHERE id={correction_delivery}")
    with pytest.raises(DBAPIError, match="ct_righe_consegna_fulfilment_bounds"):
        _force_constraints(connection)
    connection.rollback()


def test_correction_self_reference_fails(isolated_postgresql) -> None:
    connection = isolated_postgresql
    _, _, variety, order, line, delivery = _seed(connection, 886050)
    _link_order(connection, delivery, order)
    row = _delivery_line(connection, delivery, order, line, 1, variety, "1")
    connection.exec_driver_sql(f"UPDATE tpo.righe_consegna SET rettifica_riga_consegna_id={row} WHERE id={row}")
    with pytest.raises(DBAPIError, match="self reference"):
        _force_constraints(connection)
    connection.rollback()


def test_real_postgresql_corrections_states_immutability_and_movement_links(isolated_postgresql) -> None:
    connection = isolated_postgresql
    client, _, variety, order, line, delivery = _seed(connection, 890001)
    connection.exec_driver_sql(f"INSERT INTO tpo.consegne_ordini VALUES ({delivery},{order},1)")
    original = connection.exec_driver_sql(f"""
      INSERT INTO tpo.righe_consegna(consegna_id,ordine_id,riga_ordine_id,posizione,varieta_id,quantita,unita_misura,created_at,created_by)
      VALUES ({delivery},{order},{line},1,{variety},1,'SET',CURRENT_TIMESTAMP,'test-suite') RETURNING id
    """).scalar_one()
    connection.exec_driver_sql(f"UPDATE tpo.consegne SET motivazione='test-only preparation' WHERE id={delivery}")
    connection.exec_driver_sql(f"UPDATE tpo.righe_consegna SET quantita=1.000000 WHERE id={original}")
    connection.exec_driver_sql(f"UPDATE tpo.ordini SET stato='EVASO' WHERE id={order}")
    connection.exec_driver_sql(f"UPDATE tpo.consegne SET stato='CONSEGNATA',data_effettiva=CURRENT_TIMESTAMP WHERE id={delivery}")
    connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
    _checkpoint(connection)

    correction_delivery = connection.exec_driver_sql(f"INSERT INTO tpo.consegne(public_id,cliente_id,stato,data_prevista,created_by) VALUES ('CON-890010',{client},'PROGRAMMATA',CURRENT_DATE,'test-suite') RETURNING id").scalar_one()
    connection.exec_driver_sql(f"INSERT INTO tpo.consegne_ordini VALUES ({correction_delivery},{order},1)")
    correction = connection.exec_driver_sql(f"""
      INSERT INTO tpo.righe_consegna(consegna_id,ordine_id,riga_ordine_id,posizione,varieta_id,quantita,unita_misura,rettifica_riga_consegna_id,created_at,created_by)
      VALUES ({correction_delivery},{order},{line},1,{variety},-0.25,'SET',{original},CURRENT_TIMESTAMP,'test-suite') RETURNING id
    """).scalar_one()
    connection.exec_driver_sql(f"UPDATE tpo.ordini SET stato='PARZIALMENTE_EVASO' WHERE id={order}")
    connection.exec_driver_sql(f"UPDATE tpo.consegne SET stato='CONSEGNATA',data_effettiva=CURRENT_TIMESTAMP WHERE id={correction_delivery}")
    connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
    _checkpoint(connection)
    delivered = connection.exec_driver_sql(f"SELECT sum(rc.quantita) FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id WHERE rc.riga_ordine_id={line} AND c.stato='CONSEGNATA'").scalar_one()
    assert str(delivered) == "0.750000"

    zero_delivery = _new_delivery(connection, 890012, client)
    _link_order(connection, zero_delivery, order)
    _delivery_line(connection, zero_delivery, order, line, 1, variety, "-0.75", "SET", original)
    _make_effective(connection, zero_delivery, order, "APERTO")
    zero_delivered = connection.exec_driver_sql(f"SELECT sum(rc.quantita) FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id WHERE rc.riga_ordine_id={line} AND c.stato='CONSEGNATA'").scalar_one()
    assert str(zero_delivered) == "0.000000"

    chained_delivery = connection.exec_driver_sql(f"INSERT INTO tpo.consegne(public_id,cliente_id,stato,data_prevista,created_by) VALUES ('CON-890011',{client},'PROGRAMMATA',CURRENT_DATE,'test-suite') RETURNING id").scalar_one()
    connection.exec_driver_sql(f"INSERT INTO tpo.consegne_ordini VALUES ({chained_delivery},{order},1)")
    _expect_db_failure(
        connection, "ct_righe_consegna_rettifica_coerente",
        lambda: connection.exec_driver_sql(
            f"INSERT INTO tpo.righe_consegna(consegna_id,ordine_id,riga_ordine_id,posizione,varieta_id,quantita,unita_misura,rettifica_riga_consegna_id,created_at,created_by) VALUES ({chained_delivery},{order},{line},1,{variety},-0.1,'SET',{correction},CURRENT_TIMESTAMP,'test-suite')"
        ),
    )

    for sql, error in (
        (f"UPDATE tpo.consegne SET motivazione='forbidden' WHERE id={delivery}", "tr_consegne_effective_immutable"),
        (f"DELETE FROM tpo.consegne WHERE id={delivery}", "tr_consegne_effective_immutable"),
        (f"UPDATE tpo.consegne_ordini SET posizione=2 WHERE consegna_id={delivery} AND ordine_id={order}", "tr_consegne_ordini_effective_immutable"),
        (f"DELETE FROM tpo.consegne_ordini WHERE consegna_id={delivery} AND ordine_id={order}", "tr_consegne_ordini_effective_immutable"),
        (f"UPDATE tpo.righe_consegna SET quantita=0.9 WHERE id={original}", "tr_righe_consegna_effective_immutable"),
        (f"DELETE FROM tpo.righe_consegna WHERE id={original}", "tr_righe_consegna_effective_immutable"),
    ):
        _expect_db_failure(
            connection, error, lambda sql=sql: connection.exec_driver_sql(sql),
        )

    connection.exec_driver_sql(f"INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at) VALUES ({variety},2,'SET',CURRENT_TIMESTAMP)")
    connection.exec_driver_sql(f"""
      INSERT INTO tpo.movimenti_magazzino(public_id,varieta_id,unita_misura,tipo,direzione,quantita,data_movimento,motivo,origine_tipo,consegna_id,riga_consegna_id,created_by)
      VALUES ('MOV-890001',{variety},'SET','SCARICO','NEGATIVO',1,CURRENT_TIMESTAMP,'test-only','CONSEGNA',{delivery},{original},'test-suite')
    """)
    _checkpoint(connection)
    _expect_db_failure(
        connection, "fk_movimenti_magazzino_riga_consegna_consegna",
        lambda: connection.exec_driver_sql(f"""
          INSERT INTO tpo.movimenti_magazzino(public_id,varieta_id,unita_misura,tipo,direzione,quantita,data_movimento,motivo,origine_tipo,consegna_id,riga_consegna_id,created_by)
          VALUES ('MOV-890002',{variety},'SET','SCARICO','NEGATIVO',1,CURRENT_TIMESTAMP,'test-only','CONSEGNA',{correction_delivery},{original},'test-suite')
        """),
    )
    for public_id, origin in (("MOV-890003", "RACCOLTA"), ("MOV-890004", "SCARTO")):
        _expect_db_failure(
            connection, "ck_movimenti_magazzino_origine_references",
            lambda public_id=public_id, origin=origin: connection.exec_driver_sql(f"""
              INSERT INTO tpo.movimenti_magazzino(public_id,varieta_id,unita_misura,tipo,direzione,quantita,data_movimento,motivo,origine_tipo,riga_consegna_id,created_by)
              VALUES ('{public_id}',{variety},'SET','RETTIFICA','POSITIVO',1,CURRENT_TIMESTAMP,'test-only','{origin}',{original},'test-suite')
            """),
        )
    _expect_db_failure(
        connection, "ck_movimenti_magazzino_origine_references",
        lambda: connection.exec_driver_sql(f"""
          INSERT INTO tpo.movimenti_magazzino(public_id,varieta_id,unita_misura,tipo,direzione,quantita,data_movimento,motivo,origine_tipo,consegna_id,created_by)
          VALUES ('MOV-890005',{variety},'SET','SCARICO','NEGATIVO',1,CURRENT_TIMESTAMP,'test-only','CONSEGNA',{delivery},'test-suite')
        """),
    )


def test_old_new_aggregate_bypass_is_blocked_after_effective_delivery(isolated_postgresql) -> None:
    connection = isolated_postgresql
    _, _, variety, order, line, delivery = _seed(connection, 899001)
    _prepare_delivery(connection, delivery, order, line, variety, "0.5")
    _make_effective(connection, delivery, order, "PARZIALMENTE_EVASO")
    with pytest.raises(DBAPIError, match="tr_righe_consegna_effective_immutable"):
        connection.exec_driver_sql(
            f"UPDATE tpo.righe_consegna SET riga_ordine_id={line}, ordine_id={order} WHERE consegna_id={delivery}"
        )
    connection.rollback()


def test_order_state_zero_delivered_open_passes(isolated_postgresql) -> None:
    connection = isolated_postgresql
    _, _, _, order, _, _ = _seed(connection, 900001)
    connection.exec_driver_sql(f"UPDATE tpo.ordini SET stato='APERTO' WHERE id={order}")
    _force_constraints(connection)
    _checkpoint(connection)


def test_partial_delivery_half_sets_partial_state(isolated_postgresql) -> None:
    connection = isolated_postgresql
    _, _, variety, order, line, delivery = _seed(connection, 900100)
    _prepare_delivery(connection, delivery, order, line, variety, "0.5")
    _make_effective(connection, delivery, order, "PARZIALMENTE_EVASO")
    delivered = connection.exec_driver_sql(f"""
      SELECT sum(rc.quantita) FROM tpo.righe_consegna rc
      JOIN tpo.consegne c ON c.id=rc.consegna_id
      WHERE rc.riga_ordine_id={line} AND c.stato='CONSEGNATA'
    """).scalar_one()
    assert str(delivered) == "0.500000"


def test_partial_delivery_second_half_completes_order(isolated_postgresql) -> None:
    connection = isolated_postgresql
    client, _, variety, order, line, delivery = _seed(connection, 900110)
    _prepare_delivery(connection, delivery, order, line, variety, "0.5")
    _make_effective(connection, delivery, order, "PARZIALMENTE_EVASO")
    second = _new_delivery(connection, 900111, client)
    _prepare_delivery(connection, second, order, line, variety, "0.5")
    _make_effective(connection, second, order, "EVASO")
    delivered = connection.exec_driver_sql(f"""
      SELECT sum(rc.quantita) FROM tpo.righe_consegna rc
      JOIN tpo.consegne c ON c.id=rc.consegna_id
      WHERE rc.riga_ordine_id={line} AND c.stato='CONSEGNATA'
    """).scalar_one()
    assert str(delivered) == "1.000000"


def test_partial_delivery_overdelivery_fails_bounds(isolated_postgresql) -> None:
    connection = isolated_postgresql
    client, _, variety, order, line, delivery = _seed(connection, 900120)
    _prepare_delivery(connection, delivery, order, line, variety, "1")
    _make_effective(connection, delivery, order, "EVASO")
    excess = _new_delivery(connection, 900121, client)
    _prepare_delivery(connection, excess, order, line, variety, "0.1")
    connection.exec_driver_sql(
        f"UPDATE tpo.consegne SET stato='CONSEGNATA',data_effettiva=CURRENT_TIMESTAMP WHERE id={excess}"
    )
    with pytest.raises(DBAPIError, match="ct_righe_consegna_fulfilment_bounds"):
        _force_constraints(connection)
    connection.rollback()


def test_valid_correction_reopens_partial_order(isolated_postgresql) -> None:
    connection = isolated_postgresql
    client, _, variety, order, line, delivery = _seed(connection, 900130)
    original = _prepare_delivery(connection, delivery, order, line, variety, "1")
    _make_effective(connection, delivery, order, "EVASO")
    correction_delivery = _new_delivery(connection, 900131, client)
    _link_order(connection, correction_delivery, order)
    _delivery_line(
        connection, correction_delivery, order, line, 1, variety, "-0.25", "SET", original
    )
    _make_effective(connection, correction_delivery, order, "PARZIALMENTE_EVASO")
    delivered = connection.exec_driver_sql(f"""
      SELECT sum(rc.quantita) FROM tpo.righe_consegna rc
      JOIN tpo.consegne c ON c.id=rc.consegna_id
      WHERE rc.riga_ordine_id={line} AND c.stato='CONSEGNATA'
    """).scalar_one()
    ordered = connection.exec_driver_sql(
        f"SELECT quantita FROM tpo.righe_ordine WHERE id={line}"
    ).scalar_one()
    assert str(delivered) == "0.750000"
    assert str(ordered - delivered) == "0.250000"


def test_valid_correction_to_zero_reopens_order(isolated_postgresql) -> None:
    connection = isolated_postgresql
    client, _, variety, order, line, delivery = _seed(connection, 900140)
    original = _prepare_delivery(connection, delivery, order, line, variety, "1")
    _make_effective(connection, delivery, order, "EVASO")
    correction_delivery = _new_delivery(connection, 900141, client)
    _link_order(connection, correction_delivery, order)
    _delivery_line(
        connection, correction_delivery, order, line, 1, variety, "-1", "SET", original
    )
    _make_effective(connection, correction_delivery, order, "APERTO")
    delivered = connection.exec_driver_sql(f"""
      SELECT sum(rc.quantita) FROM tpo.righe_consegna rc
      JOIN tpo.consegne c ON c.id=rc.consegna_id
      WHERE rc.riga_ordine_id={line} AND c.stato='CONSEGNATA'
    """).scalar_one()
    assert str(delivered) == "0.000000"


def test_trigger_validates_but_does_not_update_order_state(isolated_postgresql) -> None:
    connection = isolated_postgresql
    _, _, variety, order, line, delivery = _seed(connection, 900010)
    _prepare_delivery(connection, delivery, order, line, variety, "0.5")
    _expect_db_failure(
        connection,
        "expected PARZIALMENTE_EVASO",
        lambda: connection.exec_driver_sql(
            f"UPDATE tpo.consegne SET stato='CONSEGNATA',data_effettiva=CURRENT_TIMESTAMP WHERE id={delivery}"
        ),
    )
    assert connection.exec_driver_sql(
        f"SELECT stato::text FROM tpo.ordini WHERE id={order}"
    ).scalar_one() == "APERTO"


def test_pre_effective_line_can_move_between_valid_aggregates(isolated_postgresql) -> None:
    connection = isolated_postgresql
    client, _, variety, order_a, line_a, delivery_a = _seed(connection, 900020)
    order_b = connection.exec_driver_sql(f"""
      INSERT INTO tpo.ordini(
        public_id,cliente_id,data_ordine,data_consegna_prevista,stato,
        tipo_creazione,created_by
      ) VALUES ('ORD-900021',{client},CURRENT_DATE,CURRENT_DATE,'APERTO',
                'MANUALE','test-suite') RETURNING id
    """).scalar_one()
    line_b = connection.exec_driver_sql(f"""
      INSERT INTO tpo.righe_ordine(
        ordine_id,posizione,varieta_id,quantita,unita_misura,public_id
      ) VALUES ({order_b},1,{variety},1,'SET','RO-900021') RETURNING id
    """).scalar_one()
    delivery_b = _new_delivery(connection, 900021, client)
    _link_order(connection, delivery_a, order_a)
    _link_order(connection, delivery_b, order_b)
    row = _delivery_line(connection, delivery_a, order_a, line_a, 1, variety, "0.5")
    # Planned rows contribute zero to fulfilment. Therefore both OLD and NEW
    # aggregates can be valid during a preparatory move; an intentionally
    # inconsistent OLD aggregate cannot be constructed without making a
    # delivery effective, at which point the immutability trigger blocks it.
    connection.exec_driver_sql(f"""
      UPDATE tpo.righe_consegna
      SET consegna_id={delivery_b},ordine_id={order_b},riga_ordine_id={line_b}
      WHERE id={row}
    """)
    _force_constraints(connection)
    assert connection.exec_driver_sql(
        f"SELECT (consegna_id,ordine_id,riga_ordine_id)::text FROM tpo.righe_consegna WHERE id={row}"
    ).scalar_one() == f"({delivery_b},{order_b},{line_b})"
    _checkpoint(connection)


def test_correction_of_correction_fails_individually(isolated_postgresql) -> None:
    connection = isolated_postgresql
    client, _, variety, order, line, delivery = _seed(connection, 900030)
    original = _prepare_delivery(connection, delivery, order, line, variety, "1")
    _make_effective(connection, delivery, order, "EVASO")
    correction_delivery = _new_delivery(connection, 900031, client)
    _link_order(connection, correction_delivery, order)
    correction = _delivery_line(
        connection, correction_delivery, order, line, 1, variety, "-0.25", "SET", original
    )
    _make_effective(connection, correction_delivery, order, "PARZIALMENTE_EVASO")
    chained_delivery = _new_delivery(connection, 900032, client)
    _link_order(connection, chained_delivery, order)
    _expect_db_failure(
        connection,
        "ct_righe_consegna_rettifica_coerente",
        lambda: _delivery_line(
            connection, chained_delivery, order, line, 1, variety, "-0.1", "SET", correction
        ),
    )
    connection.rollback()


@pytest.mark.parametrize(
    ("number", "target", "operation", "marker"),
    (
        (901001, "delivery", "update", "tr_consegne_effective_immutable"),
        (901010, "delivery", "delete", "tr_consegne_effective_immutable"),
        (901020, "join", "update", "tr_consegne_ordini_effective_immutable"),
        (901030, "join", "delete", "tr_consegne_ordini_effective_immutable"),
        (901040, "line", "update", "tr_righe_consegna_effective_immutable"),
        (901050, "line", "delete", "tr_righe_consegna_effective_immutable"),
    ),
    ids=(
        "update_delivery", "delete_delivery", "update_join",
        "delete_join", "update_line", "delete_line",
    ),
)
def test_effective_delivery_components_are_individually_immutable(
    isolated_postgresql, number, target, operation, marker,
) -> None:
    connection = isolated_postgresql
    _, _, variety, order, line, delivery = _seed(connection, number)
    delivery_row = _prepare_delivery(connection, delivery, order, line, variety, "0.5")
    _make_effective(connection, delivery, order, "PARZIALMENTE_EVASO")
    statements = {
        ("delivery", "update"): f"UPDATE tpo.consegne SET motivazione='forbidden' WHERE id={delivery}",
        ("delivery", "delete"): f"DELETE FROM tpo.consegne WHERE id={delivery}",
        ("join", "update"): f"UPDATE tpo.consegne_ordini SET posizione=2 WHERE consegna_id={delivery} AND ordine_id={order}",
        ("join", "delete"): f"DELETE FROM tpo.consegne_ordini WHERE consegna_id={delivery} AND ordine_id={order}",
        ("line", "update"): f"UPDATE tpo.righe_consegna SET quantita=0.4 WHERE id={delivery_row}",
        ("line", "delete"): f"DELETE FROM tpo.righe_consegna WHERE id={delivery_row}",
    }
    _expect_db_failure(
        connection, marker,
        lambda: connection.exec_driver_sql(statements[(target, operation)]),
    )
    connection.rollback()


def test_movement_delivery_matching_line_passes(isolated_postgresql) -> None:
    connection = isolated_postgresql
    _, _, variety, order, line, delivery = _seed(connection, 902001)
    row = _prepare_delivery(connection, delivery, order, line, variety, "1")
    _make_effective(connection, delivery, order, "EVASO")
    connection.exec_driver_sql(
        f"INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at) VALUES ({variety},2,'SET',CURRENT_TIMESTAMP)"
    )
    _movement(connection, "MOV-902001", variety, "CONSEGNA", delivery=delivery, delivery_line=row)
    _checkpoint(connection)


def test_movement_delivery_line_from_other_delivery_fails(isolated_postgresql) -> None:
    connection = isolated_postgresql
    client, _, variety, order, line, delivery = _seed(connection, 902010)
    row = _prepare_delivery(connection, delivery, order, line, variety, "1")
    _make_effective(connection, delivery, order, "EVASO")
    other_delivery = _new_delivery(connection, 902011, client)
    connection.exec_driver_sql(
        f"INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at) VALUES ({variety},2,'SET',CURRENT_TIMESTAMP)"
    )
    _expect_db_failure(
        connection, "fk_movimenti_magazzino_riga_consegna_consegna",
        lambda: _movement(
            connection, "MOV-902010", variety, "CONSEGNA",
            delivery=other_delivery, delivery_line=row,
        ),
    )
    connection.rollback()


@pytest.mark.parametrize(
    ("number", "origin", "include_delivery", "marker"),
    (
        (902020, "CONSEGNA", True, "ck_movimenti_magazzino_origine_references"),
        (902030, "RACCOLTA", False, "ck_movimenti_magazzino_origine_references"),
        (902040, "SCARTO", False, "ck_movimenti_magazzino_origine_references"),
    ),
    ids=("delivery_without_line", "harvest_with_delivery_line", "other_origin_with_delivery_line"),
)
def test_movement_origin_matrix_rejects_invalid_delivery_line(
    isolated_postgresql, number, origin, include_delivery, marker,
) -> None:
    connection = isolated_postgresql
    _, _, variety, order, line, delivery = _seed(connection, number)
    row = _prepare_delivery(connection, delivery, order, line, variety, "1")
    _make_effective(connection, delivery, order, "EVASO")
    connection.exec_driver_sql(
        f"INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at) VALUES ({variety},2,'SET',CURRENT_TIMESTAMP)"
    )
    _expect_db_failure(
        connection, marker,
        lambda: _movement(
            connection, f"MOV-{number:06d}", variety, origin,
            delivery=delivery if include_delivery else None,
            delivery_line=None if include_delivery else row,
        ),
    )
    connection.rollback()


def test_movement_harvest_with_real_foreign_key_still_passes(isolated_postgresql) -> None:
    connection = isolated_postgresql
    variety, harvest = _real_harvest(connection)
    _movement(connection, "MOV-990001", variety, "RACCOLTA", harvest=harvest)
    _checkpoint(connection)
