from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
import re

from alembic import command
import pytest
import sqlalchemy as sa

from src.tpo_core.infrastructure.postgresql.alembic import make_config


ROOT = Path(__file__).parents[3]
KNOWLEDGE_PATH = ROOT / "migrations/versions/20260810_0003_production_knowledge_prerequisites.py"
EXECUTION_PATH = ROOT / "migrations/versions/20260810_0004_production_execution_prerequisites.py"
PREREQUISITE_TABLES = {
    "cultivar", "usi_produttivi", "cultivar_usi", "protocolli",
    "protocollo_versioni", "sementi", "semente_impieghi", "lotti_seme",
    "semine", "raccolte", "consegne", "stock", "movimenti_magazzino",
}


def _database(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'main.sqlite'}")
    connection = engine.connect()
    connection.connection.driver_connection.create_function("btrim", 1, str.strip)
    schema_path = str(tmp_path / "tpo.sqlite").replace("'", "''")
    connection.exec_driver_sql(f"ATTACH DATABASE '{schema_path}' AS tpo")
    return engine, connection


@pytest.fixture
def upgraded(tmp_path: Path):
    engine, connection = _database(tmp_path)
    command.upgrade(make_config(connection=connection), "head")
    try:
        yield connection
    finally:
        connection.close()
        engine.dispose()


def _revision(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _postgresql_ddl() -> str:
    output = StringIO()
    config = make_config()
    config.set_main_option(
        "sqlalchemy.url", "postgresql+psycopg://unused:unused@invalid/tpo"
    )
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    return re.sub(r"\s+", " ", output.getvalue()).strip()


def test_upgrade_da_0002_e_reupgrade(tmp_path: Path) -> None:
    engine, connection = _database(tmp_path)
    try:
        config = make_config(connection=connection)
        command.upgrade(config, "20260806_0002")
        command.upgrade(config, "head")
        assert PREREQUISITE_TABLES <= set(sa.inspect(connection).get_table_names(schema="tpo"))
        command.downgrade(config, "20260810_0003")
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == "20260810_0003"
        execution_tables = {
            "semine", "raccolte", "consegne", "stock", "movimenti_magazzino"
        }
        assert execution_tables.isdisjoint(
            sa.inspect(connection).get_table_names(schema="tpo")
        )
        assert {
            "cultivar", "usi_produttivi", "cultivar_usi", "protocolli",
            "protocollo_versioni", "sementi", "semente_impieghi", "lotti_seme",
        } <= set(sa.inspect(connection).get_table_names(schema="tpo"))
        command.downgrade(config, "20260806_0002")
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == "20260806_0002"
        assert PREREQUISITE_TABLES.isdisjoint(sa.inspect(connection).get_table_names(schema="tpo"))
        command.upgrade(config, "head")
        assert PREREQUISITE_TABLES <= set(sa.inspect(connection).get_table_names(schema="tpo"))
    finally:
        connection.close()
        engine.dispose()


def test_enum_prerequisite_esatti() -> None:
    knowledge = _revision(KNOWLEDGE_PATH, "knowledge_prerequisites")
    execution = _revision(EXECUTION_PATH, "execution_prerequisites")
    assert knowledge.protocollo_tipo.enums == ["STANDARD", "SPERIMENTALE"]
    assert knowledge.semente_raccomandazione.enums == ["RACCOMANDATA", "UTILIZZABILE", "SCONSIGLIATA"]
    assert execution.semina_state.enums == ["AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA", "CHIUSA"]
    assert execution.semina_esito.enums == ["RACCOLTA_COMPLETA", "RACCOLTA_PARZIALE_CON_SCARTO", "SCARTO_TOTALE", "INTERRUZIONE"]
    assert execution.consegna_state.enums == ["PROGRAMMATA", "IN_PREPARAZIONE", "CONSEGNATA", "ANNULLATA"]
    assert execution.movimento_type.enums == ["CARICO", "SCARICO", "RETTIFICA"]
    assert execution.movimento_direction.enums == ["POSITIVO", "NEGATIVO"]


def test_pk_fk_unique_check_e_indici_principali(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    assert inspector.get_pk_constraint("stock", schema="tpo")["constrained_columns"] == ["varieta_id"]
    cultivar_usi_unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("cultivar_usi", schema="tpo")}
    assert ("cultivar_id", "uso_produttivo_id") in cultivar_usi_unique
    lotti_unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("lotti_seme", schema="tpo")}
    assert ("semente_id", "numero_lotto_produttore") in lotti_unique
    semine_fks = {item["referred_table"] for item in inspector.get_foreign_keys("semine", schema="tpo")}
    assert semine_fks == {"varieta", "cultivar", "cultivar_usi", "lotti_seme", "protocollo_versioni"}
    raccolte_fks = {item["referred_table"] for item in inspector.get_foreign_keys("raccolte", schema="tpo")}
    assert raccolte_fks == {"semine"}
    stock_fks = {item["referred_table"] for item in inspector.get_foreign_keys("stock", schema="tpo")}
    assert stock_fks == {"varieta", "movimenti_magazzino"}
    checks = {item["name"] for item in inspector.get_check_constraints("stock", schema="tpo")}
    assert {"ck_stock_disponibile_nonnegative", "ck_stock_version_nonnegative"} <= checks
    indexes = {item["name"] for item in inspector.get_indexes("semine", schema="tpo")}
    assert {"ix_semine_stato_data_avvio", "ix_semine_protocollo_versione_id"} <= indexes


def test_head_estende_semine_con_version_planning(upgraded) -> None:
    columns = {item["name"] for item in sa.inspect(upgraded).get_columns("semine", schema="tpo")}
    assert "version" in columns


def test_tipi_numeric_nullability_e_default_critici(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    semine = {item["name"]: item for item in inspector.get_columns("semine", schema="tpo")}
    stock = {item["name"]: item for item in inspector.get_columns("stock", schema="tpo")}
    movimenti = {
        item["name"]: item
        for item in inspector.get_columns("movimenti_magazzino", schema="tpo")
    }

    assert semine["public_id"]["nullable"] is False
    assert semine["public_id"]["default"] is None
    assert semine["stato"]["nullable"] is False
    assert semine["data_avvio"]["nullable"] is False
    assert isinstance(semine["quantita_seme"]["type"], sa.Numeric)
    assert (semine["quantita_seme"]["type"].precision, semine["quantita_seme"]["type"].scale) == (20, 6)
    assert isinstance(movimenti["quantita"]["type"], sa.Numeric)
    assert (movimenti["quantita"]["type"].precision, movimenti["quantita"]["type"].scale) == (20, 6)
    assert stock["disponibile"]["nullable"] is False
    assert str(stock["disponibile"]["default"]).strip("'\"") in {"0", "0.000000"}
    assert stock["version"]["nullable"] is False
    assert str(stock["version"]["default"]).strip("'\"") == "0"
    assert stock["updated_at"]["nullable"] is False


def test_postgresql_ddl_extension_exclusion_public_id_e_indici_funzionali() -> None:
    ddl = _postgresql_ddl()

    assert "CREATE EXTENSION IF NOT EXISTS btree_gist" in ddl
    assert "CONSTRAINT ex_protocollo_versioni_validita EXCLUDE USING gist" in ddl
    assert "protocollo_id WITH =" in ddl
    assert "daterange(valida_dal, valida_al, '[)') WITH &&" in ddl

    expected_public_id_checks = {
        "ck_semine_public_id_format": "public_id ~ '^SEM-[0-9]{6,}$'",
        "ck_raccolte_public_id_format": "public_id ~ '^RAC-[0-9]{6,}$'",
        "ck_consegne_public_id_format": "public_id ~ '^CON-[0-9]{6,}$'",
        "ck_movimenti_magazzino_public_id_format": "public_id ~ '^MOV-[0-9]{6,}$'",
    }
    for name, formula in expected_public_id_checks.items():
        assert f"CONSTRAINT {name} CHECK ({formula})" in ddl

    assert "CREATE UNIQUE INDEX uq_cultivar_varieta_denominazione_normalized" in ddl
    assert "lower(btrim(denominazione))" in ddl
    assert "CREATE UNIQUE INDEX uq_sementi_fornitore_referenza_normalized" in ddl
    assert "lower(btrim(fornitore))" in ddl
    assert "lower(btrim(referenza_commerciale))" in ddl
    assert "CREATE UNIQUE INDEX uq_protocolli_cultivar_uso_tipo_denominazione_normalized" in ddl
    assert "DROP EXTENSION" not in ddl


def test_postgresql_ddl_movement_origin_check() -> None:
    ddl = _postgresql_ddl()
    assert "CONSTRAINT ck_movimenti_magazzino_origine_references CHECK" in ddl
    assert "origine_tipo = 'RACCOLTA' AND raccolta_id IS NOT NULL AND consegna_id IS NULL" in ddl
    assert "origine_tipo = 'CONSEGNA' AND consegna_id IS NOT NULL AND raccolta_id IS NULL" in ddl
    assert "origine_tipo NOT IN ('RACCOLTA', 'CONSEGNA') AND raccolta_id IS NULL AND consegna_id IS NULL" in ddl


@pytest.fixture
def movement_origin_check(upgraded):
    inspector = sa.inspect(upgraded)
    constraints = {
        item["name"]: item["sqltext"]
        for item in inspector.get_check_constraints("movimenti_magazzino", schema="tpo")
    }
    formula = constraints["ck_movimenti_magazzino_origine_references"]
    metadata = sa.MetaData()
    table = sa.Table(
        "movement_origin_check",
        metadata,
        sa.Column("origine_tipo", sa.Text(), nullable=False),
        sa.Column("raccolta_id", sa.BigInteger()),
        sa.Column("consegna_id", sa.BigInteger()),
        sa.CheckConstraint(formula, name="ck_movimenti_magazzino_origine_references"),
    )
    metadata.create_all(upgraded)
    return upgraded, table


@pytest.mark.parametrize(
    "values",
    [
        {"origine_tipo": "RACCOLTA", "raccolta_id": 1},
        {"origine_tipo": "CONSEGNA", "consegna_id": 1},
        {"origine_tipo": "SCARTO"},
        {"origine_tipo": "RETTIFICA"},
    ],
)
def test_movement_origin_check_accetta_matrice_valida(movement_origin_check, values) -> None:
    connection, table = movement_origin_check
    connection.execute(table.insert().values(**values))


@pytest.mark.parametrize(
    "values",
    [
        {"origine_tipo": "RACCOLTA"},
        {"origine_tipo": "RACCOLTA", "raccolta_id": 1, "consegna_id": 1},
        {"origine_tipo": "CONSEGNA"},
        {"origine_tipo": "CONSEGNA", "raccolta_id": 1, "consegna_id": 1},
        {"origine_tipo": "SCARTO", "raccolta_id": 1},
        {"origine_tipo": "RETTIFICA", "consegna_id": 1},
    ],
)
def test_movement_origin_check_rifiuta_matrice_invalida(movement_origin_check, values) -> None:
    connection, table = movement_origin_check
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(table.insert().values(**values))


def test_migrazioni_non_contengono_seed_o_import_google(upgraded) -> None:
    assert upgraded.execute(sa.text("SELECT count(*) FROM tpo.id_sequences")).scalar_one() == 0
    for table in PREREQUISITE_TABLES:
        assert upgraded.execute(sa.text(f"SELECT count(*) FROM tpo.{table}")).scalar_one() == 0
    source = KNOWLEDGE_PATH.read_text(encoding="utf-8") + EXECUTION_PATH.read_text(encoding="utf-8")
    assert "op.bulk_insert" not in source
    assert "INSERT INTO" not in source.upper()
    assert "GOOGLE" not in source.upper()


def test_downgrade_prerequisite_e_conservativo() -> None:
    for path in (KNOWLEDGE_PATH, EXECUTION_PATH):
        source = path.read_text(encoding="utf-8")
        downgrade = source[source.index("def downgrade()") :]
        assert "DROP SCHEMA" not in downgrade.upper()
        assert "drop_all" not in downgrade
        assert "CASCADE" not in downgrade.upper()
