from pathlib import Path

from alembic.config import Config
from alembic import command as alembic_command
from alembic.script import ScriptDirectory
import pytest

from src.tpo_core.infrastructure.postgresql.alembic import make_config
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql


ROOT = Path(__file__).parents[3]


def test_id_sequences_backfill_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260904_0028"]
    revision = script.get_revision("20260903_0025")
    assert revision.down_revision == "20260903_0024"


def test_id_sequences_backfill_migration_contains_all_four_seeds():
    source = (
        ROOT / "migrations/versions/20260903_0025_id_sequences_backfill.py"
    ).read_text()
    for authority in (
        "MOVIMENTO_ID", "MovimentoId", '"MOV"',
        "ORDINE_ID", "OrdineId", '"ORD"',
        "CONSEGNA_ID", "ConsegnaId", '"CON"',
        "RUN_ID", "RunId", '"RUN"',
        "cannot downgrade: one or more seeded id_sequences already advanced",
    ):
        assert authority in source


def test_real_postgresql_seeds_all_four_sequences(isolated_postgresql):
    connection = isolated_postgresql
    config = make_config(connection=connection)
    alembic_command.upgrade(config, "head")
    rows = connection.exec_driver_sql(
        "SELECT sequence_name,identifier_type,prefix,next_value,version FROM tpo.id_sequences "
        "WHERE sequence_name IN ('MOVIMENTO_ID','ORDINE_ID','CONSEGNA_ID','RUN_ID') "
        "ORDER BY sequence_name"
    ).all()
    assert rows == [
        ("CONSEGNA_ID", "ConsegnaId", "CON", 1, 0),
        ("MOVIMENTO_ID", "MovimentoId", "MOV", 1, 0),
        ("ORDINE_ID", "OrdineId", "ORD", 1, 0),
        ("RUN_ID", "RunId", "RUN", 1, 0),
    ]


def test_real_postgresql_downgrade_removes_untouched_seeds(isolated_postgresql):
    connection = isolated_postgresql
    config = make_config(connection=connection)
    alembic_command.upgrade(config, "head")
    alembic_command.downgrade(config, "20260903_0024")
    count = connection.exec_driver_sql(
        "SELECT count(*) FROM tpo.id_sequences "
        "WHERE sequence_name IN ('MOVIMENTO_ID','ORDINE_ID','CONSEGNA_ID','RUN_ID')"
    ).scalar_one()
    assert count == 0
    alembic_command.upgrade(config, "head")


def test_real_postgresql_downgrade_blocked_once_a_sequence_advanced(isolated_postgresql):
    connection = isolated_postgresql
    config = make_config(connection=connection)
    alembic_command.upgrade(config, "head")
    connection.exec_driver_sql(
        "UPDATE tpo.id_sequences SET next_value=2,version=1 "
        "WHERE sequence_name='RUN_ID'"
    )
    with pytest.raises(Exception, match="one or more seeded id_sequences already advanced"):
        alembic_command.downgrade(config, "20260903_0024")
    connection.rollback()
    assert connection.exec_driver_sql(
        "SELECT version_num FROM alembic_version"
    ).scalar_one() == "20260904_0028"
