from datetime import date
from pathlib import Path
import uuid

from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa

from src.tpo_core.infrastructure.postgresql.alembic import make_config
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)

ROOT = Path(__file__).parents[3]
SOURCE_PATH = ROOT / "migrations/versions/20260904_0028_finanze_aziendali_authority.py"


def test_finanze_aziendali_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260905_0030"]
    revision = script.get_revision("20260904_0028")
    assert revision.down_revision == "20260903_0027"


def test_finanze_aziendali_migration_uses_established_offline_mode_precedent():
    source = SOURCE_PATH.read_text()
    assert "from alembic import context, op" in source
    assert "context.is_offline_mode()" in source
    assert "op.get_context().as_sql" not in source


def test_finanze_aziendali_migration_contains_frozen_guards():
    source = SOURCE_PATH.read_text()
    for fragment in (
        "INCASSO_ID", "IncassoId", "USCITA_ID", "UscitaId",
        "incasso_recording_requests", "uscita_recording_requests",
        "incasso_correzione_requests", "uscita_correzione_requests",
        "uq_incasso_recording_request_key", "uq_uscita_recording_request_key",
        "protect_incasso_authority", "protect_uscita_authority",
        "protect_incasso_recording_request", "protect_uscita_recording_request",
        "protect_incasso_correzione_request", "protect_uscita_correzione_request",
        "fn_incassi_rettifica_coerente", "fn_uscite_rettifica_coerente",
        "ck_incassi_ordinary_or_correction", "ck_uscite_ordinary_or_correction",
        "fk_incassi_fattura",
        "cannot downgrade: governed FINANZE AZIENDALI authority history exists",
    ):
        assert fragment in source


def test_finanze_aziendali_migration_has_no_net_amount_guard():
    """Owner Decision D3 (Freeze §3): nessuna guardia sull'importo/saldo netto,
    a differenza dell'equivalente RACCOLTA CORREZIONE
    (fn_check_raccolta_net_quantity / ct_raccolte_net_quantity_nonnegative)."""
    source = SOURCE_PATH.read_text()
    for forbidden in ("net_amount", "net_quantity", "NONNEGATIVE", "nonnegative"):
        assert forbidden not in source


# --- Constraint / trigger behaviour on a real, migrated PostgreSQL ---------------

@pytest.fixture(scope="module")
def finanze_engine(isolated_postgresql):
    """Materialize the migration once and seed a CLIENTE with two FATTURE."""
    cluster = isolated_postgresql.engine
    name = f"tpo_finanze_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as connection:
        config = make_config(connection=connection)
        alembic_command.upgrade(config, "head")
        connection.exec_driver_sql("""
            INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
            VALUES ('CLI-000001','Cliente Test','test',CURRENT_TIMESTAMP,'test')
        """)
        for numero in ("2026/0001", "2026/0002"):
            connection.exec_driver_sql(
                """INSERT INTO tpo.fatture
                     (numero_fattura,cliente_id,data_emissione,scadenza,totale_netto,
                      totale_igic,totale,created_by,created_at)
                   SELECT %s,id,DATE '2026-09-01',DATE '2026-10-01',100.00,7.00,107.00,
                          'test',CURRENT_TIMESTAMP
                   FROM tpo.clienti WHERE public_id='CLI-000001'""",
                (numero,),
            )
    try:
        yield engine
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def _insert_incasso(connection, public_id, *, fattura="2026/0001", importo="10.00",
                     rettifica_di=None, data=date(2026, 9, 4)):
    rettifica_pk = None
    if rettifica_di is not None:
        rettifica_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.incassi WHERE public_id=%s", (rettifica_di,)
        ).scalar_one()
    return connection.exec_driver_sql(
        """INSERT INTO tpo.incassi
             (public_id,fattura_numero,importo,data_incasso,metodo,
              rettifica_incasso_id,created_by)
           VALUES (%s,%s,%s,%s,'BONIFICO',%s,'test') RETURNING id""",
        (public_id, fattura, importo, data, rettifica_pk),
    ).scalar_one()


def _self_reference_incasso(connection, public_id):
    connection.exec_driver_sql(
        """
        WITH next_id AS (SELECT nextval(pg_get_serial_sequence('tpo.incassi','id')) AS id)
        INSERT INTO tpo.incassi
          (id,public_id,fattura_numero,importo,data_incasso,metodo,
           rettifica_incasso_id,created_by)
        SELECT next_id.id,%s,'2026/0001',-1,DATE '2026-09-04','BONIFICO',next_id.id,'test'
        FROM next_id
        """,
        (public_id,),
    )


def _insert_uscita(connection, public_id, *, importo="10.00", rettifica_di=None,
                    categoria="SEMENTI", beneficiario="Test SL", data=date(2026, 9, 4)):
    rettifica_pk = None
    if rettifica_di is not None:
        rettifica_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.uscite WHERE public_id=%s", (rettifica_di,)
        ).scalar_one()
    return connection.exec_driver_sql(
        """INSERT INTO tpo.uscite
             (public_id,importo,data_uscita,categoria,beneficiario,metodo,
              rettifica_uscita_id,created_by)
           VALUES (%s,%s,%s,%s,%s,'BONIFICO',%s,'test') RETURNING id""",
        (public_id, importo, data, categoria, beneficiario, rettifica_pk),
    ).scalar_one()


def _self_reference_uscita(connection, public_id):
    connection.exec_driver_sql(
        """
        WITH next_id AS (SELECT nextval(pg_get_serial_sequence('tpo.uscite','id')) AS id)
        INSERT INTO tpo.uscite
          (id,public_id,importo,data_uscita,categoria,beneficiario,metodo,
           rettifica_uscita_id,created_by)
        SELECT next_id.id,%s,-1,DATE '2026-09-04','SEMENTI','Test SL','BONIFICO',
               next_id.id,'test'
        FROM next_id
        """,
        (public_id,),
    )


def _force_constraints(connection) -> None:
    connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")


def _assert_connection_healthy(connection) -> None:
    assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1


def _expect_db_failure(connection, marker: str, action) -> None:
    savepoint = connection.begin_nested()
    try:
        with pytest.raises(sa.exc.DBAPIError, match=marker):
            action()
            _force_constraints(connection)
    finally:
        savepoint.rollback()
    _assert_connection_healthy(connection)


def test_ordinary_incasso_requires_positive_importo(finanze_engine):
    connection = finanze_engine.connect()
    _expect_db_failure(
        connection, "ck_incassi_ordinary_or_correction",
        lambda: _insert_incasso(connection, "INC-800001", importo="0"),
    )
    connection.close()


def test_ordinary_uscita_requires_positive_importo(finanze_engine):
    connection = finanze_engine.connect()
    _expect_db_failure(
        connection, "ck_uscite_ordinary_or_correction",
        lambda: _insert_uscita(connection, "USC-800001", importo="0"),
    )
    connection.close()


def test_incasso_correction_rejects_zero_importo(finanze_engine):
    connection = finanze_engine.connect()
    _insert_incasso(connection, "INC-800010", importo="1")
    connection.commit()
    _expect_db_failure(
        connection, "ck_incassi_ordinary_or_correction",
        lambda: _insert_incasso(
            connection, "INC-800011", importo="0", rettifica_di="INC-800010",
        ),
    )
    connection.close()


def test_incasso_self_reference_is_rejected(finanze_engine):
    connection = finanze_engine.connect()
    _expect_db_failure(
        connection, "self reference",
        lambda: _self_reference_incasso(connection, "INC-800020"),
    )
    connection.close()


def test_uscita_self_reference_is_rejected(finanze_engine):
    connection = finanze_engine.connect()
    _expect_db_failure(
        connection, "self reference",
        lambda: _self_reference_uscita(connection, "USC-800020"),
    )
    connection.close()


def test_incasso_chained_correction_is_rejected(finanze_engine):
    connection = finanze_engine.connect()
    _insert_incasso(connection, "INC-800030", importo="1")
    _insert_incasso(connection, "INC-800031", importo="-0.5", rettifica_di="INC-800030")
    connection.commit()
    _expect_db_failure(
        connection, "ct_incassi_rettifica_coerente",
        lambda: _insert_incasso(
            connection, "INC-800032", importo="-0.25", rettifica_di="INC-800031",
        ),
    )
    connection.close()


def test_uscita_chained_correction_is_rejected(finanze_engine):
    connection = finanze_engine.connect()
    _insert_uscita(connection, "USC-800030", importo="1")
    _insert_uscita(connection, "USC-800031", importo="-0.5", rettifica_di="USC-800030")
    connection.commit()
    _expect_db_failure(
        connection, "ct_uscite_rettifica_coerente",
        lambda: _insert_uscita(
            connection, "USC-800032", importo="-0.25", rettifica_di="USC-800031",
        ),
    )
    connection.close()


def test_incasso_correction_fattura_mismatch_is_rejected(finanze_engine):
    connection = finanze_engine.connect()
    _insert_incasso(connection, "INC-800040", fattura="2026/0001", importo="1")
    connection.commit()
    _expect_db_failure(
        connection, "ct_incassi_rettifica_coerente",
        lambda: _insert_incasso(
            connection, "INC-800041", fattura="2026/0002", importo="-0.5",
            rettifica_di="INC-800040",
        ),
    )
    connection.close()


def test_uscita_correction_may_reclassify_categoria_freely(finanze_engine):
    """Nessun vincolo di coerenza sulla categoria in rettifica USCITA
    (FINANZE_AZIENDALI_AUTHORITY_FREEZE.md §6, riclassificazione ammessa)."""
    connection = finanze_engine.connect()
    _insert_uscita(connection, "USC-800050", categoria="SEMENTI", importo="1")
    connection.commit()
    _insert_uscita(
        connection, "USC-800051", categoria="ATTREZZATURA", importo="-0.5",
        rettifica_di="USC-800050",
    )
    connection.commit()
    row = connection.exec_driver_sql(
        "SELECT categoria FROM tpo.uscite WHERE public_id='USC-800051'"
    ).scalar_one()
    assert row == "ATTREZZATURA"
    connection.close()


def test_incasso_metodo_check_constraint_rejects_invalid_value(finanze_engine):
    connection = finanze_engine.connect()
    with pytest.raises(sa.exc.DBAPIError, match="ck_incassi_metodo"):
        connection.exec_driver_sql(
            """INSERT INTO tpo.incassi
                 (public_id,fattura_numero,importo,data_incasso,metodo,created_by)
               VALUES ('INC-800060','2026/0001',1,DATE '2026-09-04','ASSEGNO','test')"""
        )
    connection.rollback()
    connection.close()


def test_uscita_categoria_check_constraint_rejects_invalid_value(finanze_engine):
    connection = finanze_engine.connect()
    with pytest.raises(sa.exc.DBAPIError, match="ck_uscite_categoria"):
        connection.exec_driver_sql(
            """INSERT INTO tpo.uscite
                 (public_id,importo,data_uscita,categoria,beneficiario,metodo,created_by)
               VALUES ('USC-800060',1,DATE '2026-09-04','FORNITORI','x','BONIFICO','test')"""
        )
    connection.rollback()
    connection.close()


def test_uscita_beneficiario_blank_is_rejected(finanze_engine):
    connection = finanze_engine.connect()
    with pytest.raises(sa.exc.DBAPIError, match="ck_uscite_beneficiario_not_blank"):
        connection.exec_driver_sql(
            """INSERT INTO tpo.uscite
                 (public_id,importo,data_uscita,categoria,beneficiario,metodo,created_by)
               VALUES ('USC-800070',1,DATE '2026-09-04','SEMENTI','   ','BONIFICO','test')"""
        )
    connection.rollback()
    connection.close()


def test_incasso_fattura_fk_rejects_unknown_fattura(finanze_engine):
    connection = finanze_engine.connect()
    with pytest.raises(sa.exc.DBAPIError, match="fk_incassi_fattura"):
        connection.exec_driver_sql(
            """INSERT INTO tpo.incassi
                 (public_id,fattura_numero,importo,data_incasso,metodo,created_by)
               VALUES ('INC-800080','2099/9999',1,DATE '2026-09-04','BONIFICO','test')"""
        )
    connection.rollback()
    connection.close()


def test_incassi_and_uscite_rows_are_covered_by_database_immutability(finanze_engine):
    connection = finanze_engine.connect()
    _insert_incasso(connection, "INC-800090", importo="1")
    _insert_uscita(connection, "USC-800090", importo="1")
    connection.commit()
    for statement in (
        "UPDATE tpo.incassi SET importo=2 WHERE public_id='INC-800090'",
        "DELETE FROM tpo.incassi WHERE public_id='INC-800090'",
    ):
        _expect_db_failure(
            connection, "Incasso physical fact authority is immutable",
            lambda statement=statement: connection.exec_driver_sql(statement),
        )
    for statement in (
        "UPDATE tpo.uscite SET importo=2 WHERE public_id='USC-800090'",
        "DELETE FROM tpo.uscite WHERE public_id='USC-800090'",
    ):
        _expect_db_failure(
            connection, "Uscita physical fact authority is immutable",
            lambda statement=statement: connection.exec_driver_sql(statement),
        )
    connection.close()


def test_id_sequences_seeded_for_both_registers(finanze_engine):
    connection = finanze_engine.connect()
    rows = {
        row[0]: row for row in connection.exec_driver_sql(
            "SELECT sequence_name,identifier_type,prefix,next_value FROM tpo.id_sequences "
            "WHERE sequence_name IN ('INCASSO_ID','USCITA_ID')"
        ).all()
    }
    assert rows["INCASSO_ID"] == ("INCASSO_ID", "IncassoId", "INC", 1)
    assert rows["USCITA_ID"] == ("USCITA_ID", "UscitaId", "USC", 1)
    connection.close()


# --- Downgrade guard: run in dedicated ephemeral databases ----------------------

def _fresh_database(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_finanze_downgrade_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    return name, cluster, engine


def test_real_postgresql_downgrade_blocked_once_a_recording_request_exists(isolated_postgresql):
    name, cluster, engine = _fresh_database(isolated_postgresql)
    try:
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.upgrade(config, "head")
        with engine.connect() as connection:
            config = make_config(connection=connection)
            connection.exec_driver_sql(
                """INSERT INTO tpo.incasso_recording_requests
                   (operation_scope,idempotency_key,canonical_payload_hash,incasso_id,
                    result_public_id,outcome,recorded_at,created_by)
                   VALUES ('INCASSO_RECORDING_V1','downgrade-guard',%s,NULL,NULL,
                           'RESERVED',CURRENT_TIMESTAMP,'test')""",
                ("a" * 64,),
            )
            with pytest.raises(
                Exception, match="governed FINANZE AZIENDALI authority history exists"
            ):
                alembic_command.downgrade(config, "20260903_0027")
            connection.rollback()
            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one() == "20260905_0030"
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def test_real_postgresql_downgrade_succeeds_when_untouched(isolated_postgresql):
    name, cluster, engine = _fresh_database(isolated_postgresql)
    try:
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.upgrade(config, "head")
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.downgrade(config, "20260903_0027")
            assert not sa.inspect(connection).has_table("incassi", schema="tpo")
            assert not sa.inspect(connection).has_table("uscite", schema="tpo")
            assert not sa.inspect(connection).has_table(
                "incasso_recording_requests", schema="tpo"
            )
            assert not sa.inspect(connection).has_table(
                "uscita_correzione_requests", schema="tpo"
            )
            assert connection.exec_driver_sql(
                "SELECT count(*) FROM tpo.id_sequences "
                "WHERE sequence_name IN ('INCASSO_ID','USCITA_ID')"
            ).scalar_one() == 0
            alembic_command.upgrade(config, "head")
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
