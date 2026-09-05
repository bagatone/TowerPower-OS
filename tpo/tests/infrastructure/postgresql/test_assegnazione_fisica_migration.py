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
SOURCE_PATH = ROOT / "migrations/versions/20260905_0032_assegnazione_fisica_authority.py"


def test_assegnazione_fisica_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260905_0032"]
    revision = script.get_revision("20260905_0032")
    assert revision.down_revision == "20260905_0031"


def test_assegnazione_fisica_migration_uses_established_offline_mode_precedent():
    source = SOURCE_PATH.read_text()
    assert "from alembic import context, op" in source
    assert "context.is_offline_mode()" in source
    assert "op.get_context().as_sql" not in source


def test_assegnazione_fisica_migration_contains_frozen_guards():
    source = SOURCE_PATH.read_text()
    for fragment in (
        "assegnazioni_fisiche", "assegnazione_fisica_requests",
        "uq_assegnazione_fisica_request_key", "uq_assegnazione_fisica_request_result_entity",
        "uq_assegnazione_fisica_request_result", "ck_assegnazione_fisica_request_scope",
        "ck_assegnazione_fisica_request_outcome", "ck_assegnazioni_fisiche_quantita_positive",
        "protect_assegnazione_fisica_authority", "protect_assegnazione_fisica_request",
        "cannot downgrade: governed ASSEGNAZIONE FISICA authority history exists",
    ):
        assert fragment in source


def test_assegnazione_fisica_migration_touches_no_existing_table_shape():
    # Register nuovo, append-only: nessuna modifica a raccolte/righe_ordine/consegne.
    source = SOURCE_PATH.read_text()
    for forbidden in ("add_column", "alter_column", "drop_column"):
        assert forbidden not in source


@pytest.fixture(scope="module")
def assegnazione_fisica_engine(isolated_postgresql):
    connection = isolated_postgresql
    config = make_config(connection=connection)
    alembic_command.upgrade(config, "head")
    connection.commit()
    return connection


def test_real_postgresql_upgrade_creates_governed_shapes(assegnazione_fisica_engine):
    connection = assegnazione_fisica_engine
    tables = {
        row[0] for row in connection.exec_driver_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='tpo'"
        ).all()
    }
    assert "assegnazioni_fisiche" in tables
    assert "assegnazione_fisica_requests" in tables
    row = connection.exec_driver_sql(
        "SELECT identifier_type,prefix,next_value,version FROM tpo.id_sequences "
        "WHERE sequence_name='ASSEGNAZIONE_FISICA_ID'"
    ).one()
    assert tuple(row) == ("AssegnazioneFisicaId", "ASF", 1, 0)


def _fresh_database(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_assegnazione_fisica_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    return name, cluster, engine


def test_real_postgresql_downgrade_succeeds_when_untouched(isolated_postgresql):
    name, cluster, engine = _fresh_database(isolated_postgresql)
    try:
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.upgrade(config, "head")
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.downgrade(config, "20260905_0031")
            assert not sa.inspect(connection).has_table("assegnazioni_fisiche", schema="tpo")
            assert not sa.inspect(connection).has_table(
                "assegnazione_fisica_requests", schema="tpo"
            )
            alembic_command.upgrade(config, "head")
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
