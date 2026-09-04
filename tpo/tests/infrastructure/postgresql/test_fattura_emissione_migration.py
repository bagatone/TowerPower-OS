from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest

from src.tpo_core.infrastructure.postgresql.alembic import make_config
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql

ROOT = Path(__file__).parents[3]
SOURCE_PATH = ROOT / "migrations/versions/20260903_0026_fattura_emissione.py"


def test_fattura_emissione_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260904_0028"]
    revision = script.get_revision("20260903_0026")
    assert revision.down_revision == "20260903_0025"


def test_fattura_emissione_migration_uses_established_offline_mode_precedent():
    source = SOURCE_PATH.read_text()
    assert "from alembic import context, op" in source
    assert "context.is_offline_mode()" in source
    assert "op.get_context().as_sql" not in source


def test_fattura_emissione_migration_creates_frozen_authority_shapes():
    source = SOURCE_PATH.read_text()
    for fragment in (
        "modalita_fatturazione", "termini_pagamento_giorni",
        "listino_varieta", "fattura_numerazione",
        '"fatture"', "numero_fattura", "rettifica_di",
        "fatture_consegne", "righe_fattura", "fattura_emissione_requests",
        "tr_fatture_immutable", "tr_fatture_consegne_immutable",
        "tr_righe_fattura_immutable", "tr_fattura_emissione_request_protect",
        "numero_fattura ~ '^[0-9]{4}/[0-9]{4}$'",
    ):
        assert fragment in source


def test_real_postgresql_upgrade_creates_governed_fattura_schema(isolated_postgresql):
    from alembic import command as alembic_command

    connection = isolated_postgresql
    config = make_config(connection=connection)
    alembic_command.upgrade(config, "head")
    tables = {
        row[0] for row in connection.exec_driver_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='tpo'"
        ).all()
    }
    for table in ("listino_varieta", "fattura_numerazione", "fatture",
                  "fatture_consegne", "righe_fattura", "fattura_emissione_requests"):
        assert table in tables
    columns = {
        row[0] for row in connection.exec_driver_sql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='tpo' AND table_name='clienti'"
        ).all()
    }
    assert {"modalita_fatturazione", "termini_pagamento_giorni"} <= columns


def test_real_postgresql_downgrade_blocked_once_a_fattura_exists(isolated_postgresql):
    from alembic import command as alembic_command

    connection = isolated_postgresql
    config = make_config(connection=connection)
    alembic_command.upgrade(config, "head")
    connection.exec_driver_sql("""
      INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
      VALUES ('CLI-920001','Fattura migration test','migration-test',CURRENT_TIMESTAMP,'migration-test')
    """)
    cliente_id = connection.exec_driver_sql(
        "SELECT id FROM tpo.clienti WHERE public_id='CLI-920001'"
    ).scalar_one()
    connection.exec_driver_sql("""
      INSERT INTO tpo.fatture
        (numero_fattura,cliente_id,data_emissione,scadenza,totale_netto,totale_igic,totale,
         created_at,created_by)
      VALUES ('2026/0001',%s,DATE '2026-09-03',DATE '2026-10-03',100.00,7.00,107.00,
              CURRENT_TIMESTAMP,'migration-test')
    """, (cliente_id,))
    # Deliberately NOT committed: stays visible to the downgrade check on this same
    # connection/transaction (read-your-own-writes), and a later rollback() fully
    # undoes it so the module-scoped isolated_postgresql database stays clean for
    # the next test in this module (mirrors test_id_sequences_backfill_migration.py).
    with pytest.raises(Exception, match="cannot downgrade: governed FATTURA authority history exists"):
        alembic_command.downgrade(config, "20260903_0025")
    connection.rollback()
    assert connection.exec_driver_sql(
        "SELECT version_num FROM alembic_version"
    ).scalar_one() == "20260904_0028"


def test_real_postgresql_downgrade_succeeds_when_untouched(isolated_postgresql):
    from alembic import command as alembic_command

    connection = isolated_postgresql
    config = make_config(connection=connection)
    alembic_command.upgrade(config, "head")
    alembic_command.downgrade(config, "20260903_0025")
    tables = {
        row[0] for row in connection.exec_driver_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='tpo'"
        ).all()
    }
    assert "fatture" not in tables
    alembic_command.upgrade(config, "head")
