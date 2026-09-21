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
SOURCE_PATH = ROOT / "migrations/versions/20260919_0035_stock_unita_composita.py"


def test_stock_unita_composita_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260919_0035"]
    revision = script.get_revision("20260919_0035")
    assert revision.down_revision == "20260916_0034"


def test_stock_unita_composita_migration_uses_established_offline_mode_precedent():
    source = SOURCE_PATH.read_text()
    assert "from alembic import context, op" in source
    assert "context.is_offline_mode()" in source
    assert 'bind.dialect.name != "postgresql"' in source
    assert "op.get_context().as_sql" not in source


def test_stock_unita_composita_migration_has_no_fabricated_business_rows():
    source = SOURCE_PATH.read_text()
    # L'unica DML ammessa è il backfill dell'unità su allocazioni_stock
    # (letta da tpo.stock, non un valore inventato); nessun INSERT/DELETE.
    assert "INSERT INTO" not in source
    assert "DELETE FROM" not in source
    assert source.count("op.execute(") == 1
    assert "UPDATE tpo.allocazioni_stock a SET stock_unita_misura" in source


def test_stock_unita_composita_migration_relaxes_stock_key_and_extends_allocazioni_stock():
    source = SOURCE_PATH.read_text()
    for fragment in (
        'op.add_column(\n        "allocazioni_stock"',
        "stock_unita_misura",
        'op.drop_constraint("uq_stock_varieta_unita", "stock"',
        'op.create_primary_key("pk_stock", "stock", ["varieta_id", "unita_misura"]',
        'op.create_foreign_key(\n        "fk_movimenti_magazzino_stock"',
        'op.create_foreign_key(\n        "fk_allocazioni_stock_stock_varieta", "allocazioni_stock"',
    ):
        assert fragment in source


@pytest.fixture(scope="module")
def stock_unita_composita_engine(isolated_postgresql):
    connection = isolated_postgresql
    config = make_config(connection=connection)
    alembic_command.upgrade(config, "head")
    connection.commit()
    return connection


def test_real_postgresql_upgrade_creates_composite_primary_key(stock_unita_composita_engine):
    connection = stock_unita_composita_engine
    pk_columns = [
        row[0] for row in connection.exec_driver_sql(
            """SELECT a.attname FROM pg_constraint c
               JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
               JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.attnum
               WHERE c.conrelid='tpo.stock'::regclass AND c.contype='p'
               ORDER BY k.ord"""
        ).all()
    ]
    assert pk_columns == ["varieta_id", "unita_misura"]

    unique_constraints = {
        row[0] for row in connection.exec_driver_sql(
            "SELECT conname FROM pg_constraint WHERE conrelid='tpo.stock'::regclass AND contype='u'"
        ).all()
    }
    assert "uq_stock_varieta_unita" not in unique_constraints

    columns = {
        row[0]: row[1] for row in connection.exec_driver_sql(
            "SELECT column_name,is_nullable FROM information_schema.columns "
            "WHERE table_schema='tpo' AND table_name='allocazioni_stock'"
        ).all()
    }
    assert columns.get("stock_unita_misura") == "NO"

    fk_columns = [
        row[0] for row in connection.exec_driver_sql(
            """SELECT a.attname FROM pg_constraint c
               JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
               JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.attnum
               WHERE c.conrelid='tpo.allocazioni_stock'::regclass AND c.contype='f'
                 AND c.conname='fk_allocazioni_stock_stock_varieta'
               ORDER BY k.ord"""
        ).all()
    ]
    assert fk_columns == ["stock_varieta_id", "stock_unita_misura"]


def test_real_postgresql_upgrade_allows_two_rows_per_varieta(stock_unita_composita_engine):
    connection = stock_unita_composita_engine
    varieta_id = connection.exec_driver_sql(
        """INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,updated_at,updated_by)
           VALUES ('VAR-980001','Stock composita test','ATTIVA','test-suite',CURRENT_TIMESTAMP,'test-suite')
           RETURNING id"""
    ).scalar_one()
    connection.exec_driver_sql(
        f"""INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at,version)
            VALUES ({varieta_id},0,'GRAM',CURRENT_TIMESTAMP,0)"""
    )
    # La stessa VARIETA può ora avere una seconda riga STOCK in un'altra
    # unità -- prima di questa migrazione violava la PK a colonna singola.
    connection.exec_driver_sql(
        f"""INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at,version)
            VALUES ({varieta_id},3,'SET',CURRENT_TIMESTAMP,0)"""
    )
    rows = connection.exec_driver_sql(
        f"SELECT unita_misura,disponibile FROM tpo.stock WHERE varieta_id={varieta_id} ORDER BY unita_misura"
    ).all()
    assert {(row[0], int(row[1])) for row in rows} == {("GRAM", 0), ("SET", 3)}
    connection.rollback()


def _fresh_database(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_stock_unita_composita_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    return name, cluster, engine


def test_real_postgresql_downgrade_blocked_when_a_varieta_has_two_live_rows(isolated_postgresql):
    name, cluster, engine = _fresh_database(isolated_postgresql)
    try:
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.upgrade(config, "head")
        with engine.connect() as connection:
            config = make_config(connection=connection)
            varieta_id = connection.exec_driver_sql(
                """INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,updated_at,updated_by)
                   VALUES ('VAR-980002','Stock composita downgrade guard','ATTIVA','test-suite',
                           CURRENT_TIMESTAMP,'test-suite') RETURNING id"""
            ).scalar_one()
            connection.exec_driver_sql(
                f"""INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at,version)
                    VALUES ({varieta_id},0,'GRAM',CURRENT_TIMESTAMP,0)"""
            )
            connection.exec_driver_sql(
                f"""INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at,version)
                    VALUES ({varieta_id},3,'SET',CURRENT_TIMESTAMP,0)"""
            )
            with pytest.raises(
                Exception,
                match="more than one live tpo.stock row",
            ):
                alembic_command.downgrade(config, "20260916_0034")
            connection.rollback()
            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one() == "20260919_0035"
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def test_real_postgresql_downgrade_succeeds_when_single_row_per_varieta(isolated_postgresql):
    name, cluster, engine = _fresh_database(isolated_postgresql)
    try:
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.upgrade(config, "head")
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.downgrade(config, "20260916_0034")
            pk_columns = [
                row[0] for row in connection.exec_driver_sql(
                    """SELECT a.attname FROM pg_constraint c
                       JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
                       JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.attnum
                       WHERE c.conrelid='tpo.stock'::regclass AND c.contype='p'
                       ORDER BY k.ord"""
                ).all()
            ]
            assert pk_columns == ["varieta_id"]
            column_names = {
                column["name"] for column in sa.inspect(connection).get_columns(
                    "allocazioni_stock", schema="tpo"
                )
            }
            assert "stock_unita_misura" not in column_names
            alembic_command.upgrade(config, "head")
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
