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
SOURCE_PATH = ROOT / "migrations/versions/20260905_0031_articolo_authority.py"


def test_articolo_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260905_0032"]
    revision = script.get_revision("20260905_0031")
    assert revision.down_revision == "20260905_0030"


def test_articolo_migration_uses_established_offline_mode_precedent():
    source = SOURCE_PATH.read_text()
    assert "from alembic import context, op" in source
    assert "context.is_offline_mode()" in source
    assert "op.get_context().as_sql" not in source


def test_articolo_migration_contains_frozen_guards():
    source = SOURCE_PATH.read_text()
    for fragment in (
        "articoli", "stock_articoli", "articolo_commissioning_requests",
        "movimento_articolo_requests", "ck_movimenti_magazzino_risorsa_xor",
        "fk_movimenti_magazzino_articolo_stock", "uq_stock_articoli_articolo_unita",
        "ck_stock_articoli_disponibile_nonnegative",
        "protect_articolo_constitutive_authority",
        "protect_articolo_commissioning_request",
        "protect_movimento_articolo_request",
        "cannot downgrade: governed ARTICOLO authority history exists",
    ):
        assert fragment in source


def test_articolo_migration_relaxes_varieta_id_and_adds_articolo_id():
    source = SOURCE_PATH.read_text()
    assert 'batch_alter_table("movimenti_magazzino"' in source
    assert 'alter_column("varieta_id"' in source
    assert 'add_column(sa.Column("articolo_id"' in source


def test_articolo_migration_touches_no_existing_stock_or_raccolte_shape():
    # STOCK_ARTICOLI e' una tabella parallela: tpo.stock e tpo.raccolte non
    # vengono toccate (§3 del freeze) -- nessuna operazione strutturale le
    # referenzia direttamente (i riferimenti nel docstring/commenti sono
    # prosa, non chiamate Alembic).
    source = SOURCE_PATH.read_text()
    for forbidden in (
        'op.create_table(\n        "stock"', 'op.add_column("stock"',
        'batch_alter_table("stock"', 'op.create_table(\n        "raccolte"',
        'op.add_column("raccolte"', 'batch_alter_table("raccolte"',
    ):
        assert forbidden not in source


@pytest.fixture(scope="module")
def articolo_engine(isolated_postgresql):
    connection = isolated_postgresql
    config = make_config(connection=connection)
    alembic_command.upgrade(config, "head")
    connection.commit()
    return connection


def test_real_postgresql_upgrade_creates_governed_shapes(articolo_engine):
    connection = articolo_engine
    tables = {
        row[0] for row in connection.exec_driver_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='tpo'"
        ).all()
    }
    for table in ("articoli", "stock_articoli", "articolo_commissioning_requests",
                  "movimento_articolo_requests"):
        assert table in tables
    columns = {
        row[0] for row in connection.exec_driver_sql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='tpo' AND table_name='movimenti_magazzino'"
        ).all()
    }
    assert {"varieta_id", "articolo_id"} <= columns
    is_nullable = connection.exec_driver_sql(
        "SELECT is_nullable FROM information_schema.columns WHERE table_schema='tpo' "
        "AND table_name='movimenti_magazzino' AND column_name='varieta_id'"
    ).scalar_one()
    assert is_nullable == "YES"


def test_real_postgresql_id_sequence_seeded(articolo_engine):
    connection = articolo_engine
    row = connection.exec_driver_sql(
        "SELECT identifier_type,prefix,next_value,version FROM tpo.id_sequences "
        "WHERE sequence_name='ARTICOLO_ID'"
    ).one()
    assert tuple(row) == ("ArticoloId", "ART", 1, 0)


def _fresh_database(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_articolo_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    return name, cluster, engine


def test_real_postgresql_downgrade_blocked_once_an_articolo_exists(isolated_postgresql):
    name, cluster, engine = _fresh_database(isolated_postgresql)
    try:
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.upgrade(config, "head")
        with engine.connect() as connection:
            config = make_config(connection=connection)
            connection.exec_driver_sql(
                """INSERT INTO tpo.articoli (public_id,denominazione,unita_misura,created_by)
                   VALUES ('ART-000001','Substrato fibra di cocco','GRAM','test')"""
            )
            with pytest.raises(
                Exception, match="governed ARTICOLO authority history exists"
            ):
                alembic_command.downgrade(config, "20260905_0030")
            connection.rollback()
            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one() == "20260905_0032"
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
            alembic_command.downgrade(config, "20260905_0030")
            assert not sa.inspect(connection).has_table("articoli", schema="tpo")
            assert not sa.inspect(connection).has_table("stock_articoli", schema="tpo")
            columns = {
                row[0] for row in connection.exec_driver_sql(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='tpo' AND table_name='movimenti_magazzino'"
                ).all()
            }
            assert "articolo_id" not in columns
            alembic_command.upgrade(config, "head")
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
