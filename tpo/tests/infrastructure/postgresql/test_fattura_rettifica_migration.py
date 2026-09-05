from __future__ import annotations

from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa

from src.tpo_core.infrastructure.postgresql.alembic import make_config
from tests.infrastructure.postgresql.test_fattura_emissione_writer import (
    _command as _emissione_command,
    _seed,
    _writer as _emissione_writer,
    fattura_postgresql_cluster_engine,
    fattura_postgresql_engine,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql as migration_postgresql,
)

ROOT = Path(__file__).parents[3]
SOURCE_PATH = ROOT / "migrations/versions/20260905_0029_fattura_rettifica.py"


def test_fattura_rettifica_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260905_0032"]
    revision = script.get_revision("20260905_0029")
    assert revision.down_revision == "20260904_0028"


def test_fattura_rettifica_migration_uses_established_offline_mode_precedent():
    source = SOURCE_PATH.read_text()
    assert "from alembic import context, op" in source
    assert "context.is_offline_mode()" in source
    assert "op.get_context().as_sql" not in source


def test_fattura_rettifica_migration_contains_frozen_shapes():
    source = SOURCE_PATH.read_text()
    for fragment in (
        "rettifica_riga_fattura_id", "ck_righe_fattura_ordinaria_o_rettifica",
        "uq_righe_fattura_rettifica_riga_fattura", "fattura_rettifica_requests",
        "fn_righe_fattura_rettifica_coerente", "fn_fatture_rettifica_cliente_coerente",
        "tr_fattura_rettifica_request_protect",
        "cannot downgrade: governed RECTIFY FATTURA authority history exists",
    ):
        assert fragment in source


def test_real_postgresql_upgrade_creates_governed_shapes(fattura_postgresql_engine):
    engine = fattura_postgresql_engine
    with engine.connect() as connection:
        tables = {
            row[0] for row in connection.exec_driver_sql(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='tpo'"
            ).all()
        }
        assert "fattura_rettifica_requests" in tables
        columns = {
            row[0] for row in connection.exec_driver_sql(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='tpo' AND table_name='righe_fattura'"
            ).all()
        }
        assert "rettifica_riga_fattura_id" in columns
        nullable = connection.exec_driver_sql(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema='tpo' AND table_name='righe_fattura' "
            "AND column_name='riga_consegna_id'"
        ).scalar_one()
        assert nullable == "YES"


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


def _seed_original_riga(engine, number: int):
    """Emette davvero una FATTURA con una RIGA_FATTURA ordinaria, cosi' i test sui
    trigger di coerenza della rettifica hanno una riga originale reale (con
    riga_consegna_id valorizzato) da referenziare, invece di aggirare le FK con
    INSERT manuali."""
    _seed(engine, number)
    return _emissione_writer(engine).emit(_emissione_command(number))


def test_ck_righe_fattura_ordinaria_o_rettifica_rejects_both_null(fattura_postgresql_engine):
    engine = fattura_postgresql_engine
    emitted = _seed_original_riga(engine, 950001)
    with engine.connect() as connection:
        _expect_db_failure(
            connection, "ck_righe_fattura_ordinaria_o_rettifica",
            lambda: connection.exec_driver_sql(
                """INSERT INTO tpo.righe_fattura
                     (fattura_id,riga_consegna_id,posizione,varieta_id,quantita,unita_misura,
                      prezzo_unitario,aliquota_igic,importo_netto,importo_igic,
                      rettifica_riga_fattura_id,created_at,created_by)
                   SELECT fattura_id,NULL,99,varieta_id,0,unita_misura,prezzo_unitario,
                          aliquota_igic,0,0,NULL,CURRENT_TIMESTAMP,'migration-test'
                   FROM tpo.righe_fattura WHERE fattura_id=%s LIMIT 1""",
                (emitted.fattura_id,),
            ),
        )


def test_ck_righe_fattura_ordinaria_o_rettifica_rejects_both_set(fattura_postgresql_engine):
    engine = fattura_postgresql_engine
    emitted = _seed_original_riga(engine, 950002)
    with engine.connect() as connection:
        original_riga_id = connection.exec_driver_sql(
            "SELECT id FROM tpo.righe_fattura WHERE fattura_id=%s LIMIT 1", (emitted.fattura_id,),
        ).scalar_one()
        _expect_db_failure(
            connection, "ck_righe_fattura_ordinaria_o_rettifica",
            lambda: connection.exec_driver_sql(
                """INSERT INTO tpo.righe_fattura
                     (fattura_id,riga_consegna_id,posizione,varieta_id,quantita,unita_misura,
                      prezzo_unitario,aliquota_igic,importo_netto,importo_igic,
                      rettifica_riga_fattura_id,created_at,created_by)
                   SELECT fattura_id,riga_consegna_id,98,varieta_id,-1,unita_misura,
                          prezzo_unitario,aliquota_igic,0,0,%s,CURRENT_TIMESTAMP,'migration-test'
                   FROM tpo.righe_fattura WHERE fattura_id=%s LIMIT 1""",
                (original_riga_id, emitted.fattura_id),
            ),
        )


def test_righe_fattura_rettifica_self_reference_is_rejected(fattura_postgresql_engine):
    engine = fattura_postgresql_engine
    emitted = _seed_original_riga(engine, 950003)
    with engine.connect() as connection:
        varieta_id = connection.exec_driver_sql(
            "SELECT varieta_id FROM tpo.righe_fattura WHERE fattura_id=%s LIMIT 1",
            (emitted.fattura_id,),
        ).scalar_one()
        new_fattura_id = connection.exec_driver_sql(
            """INSERT INTO tpo.fatture
                 (numero_fattura,cliente_id,data_emissione,scadenza,totale_netto,totale_igic,
                  totale,rettifica_di,created_at,created_by)
               SELECT '2026/8001',cliente_id,DATE '2026-09-05',DATE '2026-10-05',-1,0,-1,
                      numero_fattura,CURRENT_TIMESTAMP,'migration-test'
               FROM tpo.fatture WHERE id=%s RETURNING id""",
            (emitted.fattura_id,),
        ).scalar_one()
        _expect_db_failure(
            connection, "self reference",
            lambda: connection.exec_driver_sql(
                """WITH next_id AS (SELECT nextval(pg_get_serial_sequence('tpo.righe_fattura','id')) AS id)
                   INSERT INTO tpo.righe_fattura
                     (id,fattura_id,riga_consegna_id,posizione,varieta_id,quantita,unita_misura,
                      prezzo_unitario,aliquota_igic,importo_netto,importo_igic,
                      rettifica_riga_fattura_id,created_at,created_by)
                   SELECT next_id.id,%s,NULL,1,%s,-1,'GRAM',1,0,0,0,next_id.id,
                          CURRENT_TIMESTAMP,'migration-test'
                   FROM next_id""",
                (new_fattura_id, varieta_id),
            ),
        )


def test_righe_fattura_rettifica_varieta_mismatch_is_rejected(fattura_postgresql_engine):
    engine = fattura_postgresql_engine
    emitted = _seed_original_riga(engine, 950004)
    with engine.connect() as connection:
        original = connection.exec_driver_sql(
            "SELECT id,varieta_id,unita_misura,prezzo_unitario,aliquota_igic "
            "FROM tpo.righe_fattura WHERE fattura_id=%s LIMIT 1",
            (emitted.fattura_id,),
        ).fetchone()
        other_varieta_id = connection.exec_driver_sql(
            """INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,updated_at,updated_by)
               VALUES ('VAR-999998','Altra varieta','ATTIVA','migration-test',CURRENT_TIMESTAMP,
                       'migration-test') RETURNING id"""
        ).scalar_one()
        new_fattura_id = connection.exec_driver_sql(
            """INSERT INTO tpo.fatture
                 (numero_fattura,cliente_id,data_emissione,scadenza,totale_netto,totale_igic,
                  totale,rettifica_di,created_at,created_by)
               SELECT '2026/8002',cliente_id,DATE '2026-09-05',DATE '2026-10-05',-1,0,-1,
                      numero_fattura,CURRENT_TIMESTAMP,'migration-test'
               FROM tpo.fatture WHERE id=%s RETURNING id""",
            (emitted.fattura_id,),
        ).scalar_one()
        _expect_db_failure(
            connection, "ct_righe_fattura_rettifica_coerente",
            lambda: connection.exec_driver_sql(
                """INSERT INTO tpo.righe_fattura
                     (fattura_id,riga_consegna_id,posizione,varieta_id,quantita,unita_misura,
                      prezzo_unitario,aliquota_igic,importo_netto,importo_igic,
                      rettifica_riga_fattura_id,created_at,created_by)
                   VALUES (%s,NULL,1,%s,-1,%s,%s,%s,0,0,%s,CURRENT_TIMESTAMP,'migration-test')""",
                (new_fattura_id, other_varieta_id, original[2], original[3], original[4],
                 original[0]),
            ),
        )


def test_righe_fattura_rettifica_fattura_rettifica_di_mismatch_is_rejected(fattura_postgresql_engine):
    engine = fattura_postgresql_engine
    first = _seed_original_riga(engine, 950005)
    second = _seed_original_riga(engine, 950006)
    with engine.connect() as connection:
        original = connection.exec_driver_sql(
            "SELECT id,varieta_id,unita_misura,prezzo_unitario,aliquota_igic "
            "FROM tpo.righe_fattura WHERE fattura_id=%s LIMIT 1", (first.fattura_id,),
        ).fetchone()
        # una nuova FATTURA rettificativa che referenzia (rettifica_di) la SECONDA
        # fattura originale, ma la cui riga rettificativa punta a una riga della PRIMA:
        # deve essere respinta (coerenza fattura/riga).
        new_fattura_id = connection.exec_driver_sql(
            """INSERT INTO tpo.fatture
                 (numero_fattura,cliente_id,data_emissione,scadenza,totale_netto,totale_igic,
                  totale,rettifica_di,created_at,created_by)
               SELECT '2026/8003',cliente_id,DATE '2026-09-05',DATE '2026-10-05',-1,0,-1,
                      numero_fattura,CURRENT_TIMESTAMP,'migration-test'
               FROM tpo.fatture WHERE id=%s RETURNING id""",
            (second.fattura_id,),
        ).scalar_one()
        _expect_db_failure(
            connection, "ct_righe_fattura_rettifica_coerente",
            lambda: connection.exec_driver_sql(
                """INSERT INTO tpo.righe_fattura
                     (fattura_id,riga_consegna_id,posizione,varieta_id,quantita,unita_misura,
                      prezzo_unitario,aliquota_igic,importo_netto,importo_igic,
                      rettifica_riga_fattura_id,created_at,created_by)
                   VALUES (%s,NULL,1,%s,-1,%s,%s,%s,0,0,%s,CURRENT_TIMESTAMP,'migration-test')""",
                (new_fattura_id, original[1], original[2], original[3], original[4],
                 original[0]),
            ),
        )


def test_uq_righe_fattura_rettifica_riga_fattura_rejects_double_correction(fattura_postgresql_engine):
    engine = fattura_postgresql_engine
    emitted = _seed_original_riga(engine, 950007)
    with engine.connect() as connection:
        original = connection.exec_driver_sql(
            "SELECT id,varieta_id,unita_misura,prezzo_unitario,aliquota_igic "
            "FROM tpo.righe_fattura WHERE fattura_id=%s LIMIT 1", (emitted.fattura_id,),
        ).fetchone()
        new_fattura_id = connection.exec_driver_sql(
            """INSERT INTO tpo.fatture
                 (numero_fattura,cliente_id,data_emissione,scadenza,totale_netto,totale_igic,
                  totale,rettifica_di,created_at,created_by)
               SELECT '2026/8004',cliente_id,DATE '2026-09-05',DATE '2026-10-05',-1,0,-1,
                      numero_fattura,CURRENT_TIMESTAMP,'migration-test'
               FROM tpo.fatture WHERE id=%s RETURNING id""",
            (emitted.fattura_id,),
        ).scalar_one()
        connection.exec_driver_sql(
            """INSERT INTO tpo.righe_fattura
                 (fattura_id,riga_consegna_id,posizione,varieta_id,quantita,unita_misura,
                  prezzo_unitario,aliquota_igic,importo_netto,importo_igic,
                  rettifica_riga_fattura_id,created_at,created_by)
               VALUES (%s,NULL,1,%s,-1,%s,%s,%s,0,0,%s,CURRENT_TIMESTAMP,'migration-test')""",
            (new_fattura_id, original[1], original[2], original[3], original[4], original[0]),
        )
        connection.commit()
        second_fattura_id = connection.exec_driver_sql(
            """INSERT INTO tpo.fatture
                 (numero_fattura,cliente_id,data_emissione,scadenza,totale_netto,totale_igic,
                  totale,rettifica_di,created_at,created_by)
               SELECT '2026/8005',cliente_id,DATE '2026-09-05',DATE '2026-10-05',-1,0,-1,
                      numero_fattura,CURRENT_TIMESTAMP,'migration-test'
               FROM tpo.fatture WHERE id=%s RETURNING id""",
            (emitted.fattura_id,),
        ).scalar_one()
        connection.commit()
        _expect_db_failure(
            connection, "uq_righe_fattura_rettifica_riga_fattura",
            lambda: connection.exec_driver_sql(
                """INSERT INTO tpo.righe_fattura
                     (fattura_id,riga_consegna_id,posizione,varieta_id,quantita,unita_misura,
                      prezzo_unitario,aliquota_igic,importo_netto,importo_igic,
                      rettifica_riga_fattura_id,created_at,created_by)
                   VALUES (%s,NULL,1,%s,-1,%s,%s,%s,0,0,%s,CURRENT_TIMESTAMP,'migration-test')""",
                (second_fattura_id, original[1], original[2], original[3], original[4],
                 original[0]),
            ),
        )


def test_fatture_rettifica_cliente_mismatch_is_rejected(fattura_postgresql_engine):
    engine = fattura_postgresql_engine
    emitted = _seed_original_riga(engine, 950008)
    with engine.connect() as connection:
        other_cliente_id = connection.exec_driver_sql(
            """INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
               VALUES ('CLI-999998','Altro cliente','migration-test',CURRENT_TIMESTAMP,
                       'migration-test') RETURNING id"""
        ).scalar_one()
        numero_fattura_originale = connection.exec_driver_sql(
            "SELECT numero_fattura FROM tpo.fatture WHERE id=%s", (emitted.fattura_id,),
        ).scalar_one()
        _expect_db_failure(
            connection, "ct_fatture_rettifica_cliente_coerente",
            lambda: connection.exec_driver_sql(
                """INSERT INTO tpo.fatture
                     (numero_fattura,cliente_id,data_emissione,scadenza,totale_netto,totale_igic,
                      totale,rettifica_di,created_at,created_by)
                   VALUES ('2026/8006',%s,DATE '2026-09-05',DATE '2026-10-05',-1,0,-1,%s,
                           CURRENT_TIMESTAMP,'migration-test')""",
                (other_cliente_id, numero_fattura_originale),
            ),
        )


def test_real_postgresql_downgrade_blocked_once_a_rettifica_riga_exists(fattura_postgresql_engine):
    engine = fattura_postgresql_engine
    emitted = _seed_original_riga(engine, 950009)
    with engine.begin() as connection:
        original = connection.exec_driver_sql(
            "SELECT id,varieta_id,unita_misura,prezzo_unitario,aliquota_igic "
            "FROM tpo.righe_fattura WHERE fattura_id=%s LIMIT 1", (emitted.fattura_id,),
        ).fetchone()
        new_fattura_id = connection.exec_driver_sql(
            """INSERT INTO tpo.fatture
                 (numero_fattura,cliente_id,data_emissione,scadenza,totale_netto,totale_igic,
                  totale,rettifica_di,created_at,created_by)
               SELECT '2026/8007',cliente_id,DATE '2026-09-05',DATE '2026-10-05',-1,0,-1,
                      numero_fattura,CURRENT_TIMESTAMP,'migration-test'
               FROM tpo.fatture WHERE id=%s RETURNING id""",
            (emitted.fattura_id,),
        ).scalar_one()
        connection.exec_driver_sql(
            """INSERT INTO tpo.righe_fattura
                 (fattura_id,riga_consegna_id,posizione,varieta_id,quantita,unita_misura,
                  prezzo_unitario,aliquota_igic,importo_netto,importo_igic,
                  rettifica_riga_fattura_id,created_at,created_by)
               VALUES (%s,NULL,1,%s,-1,%s,%s,%s,0,0,%s,CURRENT_TIMESTAMP,'migration-test')""",
            (new_fattura_id, original[1], original[2], original[3], original[4], original[0]),
        )
        config_conn = make_config(connection=connection)
        with pytest.raises(
            Exception, match="cannot downgrade: governed RECTIFY FATTURA authority history exists"
        ):
            alembic_command.downgrade(config_conn, "20260904_0028")
        connection.rollback()
