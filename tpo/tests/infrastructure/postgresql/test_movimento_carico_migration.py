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
SOURCE_PATH = ROOT / "migrations/versions/20260905_0030_movimento_carico_raccolta.py"


def test_movimento_carico_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260905_0030"]
    revision = script.get_revision("20260905_0030")
    assert revision.down_revision == "20260905_0029"


def test_movimento_carico_migration_uses_established_offline_mode_precedent():
    source = SOURCE_PATH.read_text()
    assert "from alembic import context, op" in source
    assert "context.is_offline_mode()" in source
    assert "op.get_context().as_sql" not in source


def test_movimento_carico_migration_contains_frozen_guards():
    source = SOURCE_PATH.read_text()
    for fragment in (
        "movimento_carico_requests", "uq_movimento_carico_request_key",
        "uq_movimento_carico_movimento", "uq_movimento_carico_result",
        "ck_movimento_carico_scope", "ck_movimento_carico_outcome",
        "protect_movimento_carico_request",
        "cannot downgrade: governed MOVIMENTO CARICO authority history exists",
    ):
        assert fragment in source


def test_movimento_carico_migration_has_no_business_dml():
    source = SOURCE_PATH.read_text()
    for statement in ("INSERT INTO", "UPDATE tpo.", "DELETE FROM"):
        assert statement not in source
    assert "id_sequences" not in source


def test_movimento_carico_migration_touches_no_existing_table_shape():
    # Nessuna colonna aggiunta/rimossa/alterata e nessun nuovo CHECK su
    # movimenti_magazzino/stock/raccolte: lo schema esistente già ammette
    # origine_tipo='RACCOLTA' (§2 del freeze). L'unica modifica additiva a
    # movimenti_magazzino è la UNIQUE(id, public_id) richiesta dalla FK
    # composita (stesso precedente di raccolte, 20260830_0022), verificata
    # sotto (test_movimento_carico_migration_adds_only_the_composite_unique_constraint).
    source = SOURCE_PATH.read_text()
    for forbidden in ("add_column", "alter_column", "drop_column", "create_check_constraint"):
        assert forbidden not in source


def test_movimento_carico_migration_adds_only_the_composite_unique_constraint():
    source = SOURCE_PATH.read_text()
    assert "uq_movimenti_magazzino_id_public_id" in source
    assert 'batch_alter_table("movimenti_magazzino"' in source
    assert "create_unique_constraint" in source
    assert "drop_constraint" in source


@pytest.fixture(scope="module")
def movimento_carico_engine(isolated_postgresql):
    connection = isolated_postgresql
    config = make_config(connection=connection)
    alembic_command.upgrade(config, "head")
    connection.commit()
    return connection


def test_real_postgresql_upgrade_creates_governed_shapes(movimento_carico_engine):
    connection = movimento_carico_engine
    tables = {
        row[0] for row in connection.exec_driver_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='tpo'"
        ).all()
    }
    assert "movimento_carico_requests" in tables
    columns = {
        row[0] for row in connection.exec_driver_sql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='tpo' AND table_name='movimento_carico_requests'"
        ).all()
    }
    assert {
        "operation_scope", "idempotency_key", "canonical_payload_hash",
        "movimento_id", "result_public_id", "outcome", "recorded_at", "created_by",
    } <= columns


def _fresh_database(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_movimento_carico_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    return name, cluster, engine


def test_real_postgresql_downgrade_blocked_once_a_request_exists(isolated_postgresql):
    name, cluster, engine = _fresh_database(isolated_postgresql)
    try:
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.upgrade(config, "head")
        with engine.connect() as connection:
            config = make_config(connection=connection)
            connection.exec_driver_sql(
                """INSERT INTO tpo.movimento_carico_requests
                   (operation_scope,idempotency_key,canonical_payload_hash,movimento_id,
                    result_public_id,outcome,recorded_at,created_by)
                   VALUES ('MOVIMENTO_CARICO_RACCOLTA_V1','downgrade-guard',%s,NULL,NULL,
                           'RESERVED',CURRENT_TIMESTAMP,'test')""",
                ("a" * 64,),
            )
            with pytest.raises(
                Exception, match="governed MOVIMENTO CARICO authority history exists"
            ):
                alembic_command.downgrade(config, "20260905_0029")
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
            alembic_command.downgrade(config, "20260905_0029")
            assert not sa.inspect(connection).has_table(
                "movimento_carico_requests", schema="tpo"
            )
            alembic_command.upgrade(config, "head")
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
