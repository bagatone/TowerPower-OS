from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import command
import pytest
import sqlalchemy as sa

from src.tpo_core.infrastructure.postgresql.alembic import make_config


ROOT = Path(__file__).parents[3]
REVISION_PATH = ROOT / "migrations/versions/20260806_0002_order_commit_schema.py"
FOUNDATION_TABLES = {"id_sequences", "runs", "run_messaggi", "run_log"}
ORDER_COMMIT_TABLES = {
    "clienti", "varieta", "programmi_fornitura",
    "programmi_fornitura_versioni", "righe_programma_fornitura",
    "righe_programma_giorni", "ordini", "righe_ordine",
    "origini_righe_ordine", "audit_eventi",
}


def _revision():
    spec = importlib.util.spec_from_file_location("order_commit_revision", REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


def test_enum_ordine_creation_type_esatto_e_ordinato() -> None:
    revision = _revision()
    enum = revision.ordine_creation_type
    assert enum.name == "ordine_creation_type"
    assert enum.schema == "tpo"
    assert enum.enums == ["AUTOMATICO", "MANUALE"]
    assert enum in revision.ENUMS
    assert revision.ENUMS.index(enum) < revision.ENUMS.index(revision.audit_operation)


def test_colonna_tipo_creazione_not_null_senza_default(upgraded) -> None:
    columns = {item["name"]: item for item in sa.inspect(upgraded).get_columns("ordini", schema="tpo")}
    column = columns["tipo_creazione"]
    assert column["nullable"] is False
    assert column["default"] is None


CHECK = """
((tipo_creazione = 'AUTOMATICO' AND run_id IS NOT NULL
  AND programma_fornitura_id IS NOT NULL
  AND data_consegna_prevista IS NOT NULL
  AND chiave_idempotenza IS NOT NULL)
 OR
 (tipo_creazione = 'MANUALE' AND run_id IS NULL
  AND programma_fornitura_id IS NULL
  AND chiave_idempotenza IS NULL))
"""


@pytest.fixture
def check_connection():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = sa.Table(
        "ordine_check", metadata,
        sa.Column("tipo_creazione", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Integer()),
        sa.Column("programma_fornitura_id", sa.Integer()),
        sa.Column("data_consegna_prevista", sa.Date()),
        sa.Column("chiave_idempotenza", sa.Text()),
        sa.CheckConstraint(CHECK, name="ck_ordini_tipo_creazione_metadati"),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        yield connection, table
    engine.dispose()


@pytest.mark.parametrize(
    "values",
    [
        {"tipo_creazione": "AUTOMATICO", "run_id": 1, "programma_fornitura_id": 1,
         "data_consegna_prevista": "2026-08-06", "chiave_idempotenza": "key"},
        {"tipo_creazione": "MANUALE"},
        {"tipo_creazione": "MANUALE", "data_consegna_prevista": "2026-08-06"},
        {"tipo_creazione": "MANUALE", "data_consegna_prevista": None},
    ],
)
def test_check_tipo_creazione_accetta_combinazioni_valide(check_connection, values) -> None:
    connection, table = check_connection
    if isinstance(values.get("data_consegna_prevista"), str):
        values = values | {"data_consegna_prevista": sa.func.date(values["data_consegna_prevista"])}
    connection.execute(table.insert().values(**values))


@pytest.mark.parametrize(
    "values",
    [
        {"tipo_creazione": "AUTOMATICO", "programma_fornitura_id": 1,
         "data_consegna_prevista": sa.func.date("2026-08-06"), "chiave_idempotenza": "key"},
        {"tipo_creazione": "AUTOMATICO", "run_id": 1,
         "data_consegna_prevista": sa.func.date("2026-08-06"), "chiave_idempotenza": "key"},
        {"tipo_creazione": "AUTOMATICO", "run_id": 1, "programma_fornitura_id": 1,
         "chiave_idempotenza": "key"},
        {"tipo_creazione": "AUTOMATICO", "run_id": 1, "programma_fornitura_id": 1,
         "data_consegna_prevista": sa.func.date("2026-08-06")},
        {"tipo_creazione": "MANUALE", "run_id": 1},
        {"tipo_creazione": "MANUALE", "programma_fornitura_id": 1},
        {"tipo_creazione": "MANUALE", "chiave_idempotenza": "key"},
        {"tipo_creazione": "SCONOSCIUTO"},
    ],
)
def test_check_tipo_creazione_rifiuta_combinazioni_invalide(check_connection, values) -> None:
    connection, table = check_connection
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(table.insert().values(**values))


def _foreign_keys(inspector, table: str):
    return {
        (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"])):
        (fk.get("options") or {}).get("onupdate", "NO ACTION") + "/" +
        (fk.get("options") or {}).get("ondelete", "NO ACTION")
        for fk in inspector.get_foreign_keys(table, schema="tpo")
    }


def test_foreign_keys_esatte(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    expected = {
        "programmi_fornitura": {(('cliente_id',), 'clienti', ('id',)): "RESTRICT/RESTRICT"},
        "programmi_fornitura_versioni": {
            (("programma_fornitura_id", "cliente_id"), "programmi_fornitura", ("id", "cliente_id")): "RESTRICT/RESTRICT"
        },
        "righe_programma_fornitura": {
            (("programma_versione_id",), "programmi_fornitura_versioni", ("id",)): "RESTRICT/CASCADE",
            (("varieta_id",), "varieta", ("id",)): "RESTRICT/RESTRICT",
        },
        "righe_programma_giorni": {(('riga_programma_id',), 'righe_programma_fornitura', ('id',)): "RESTRICT/CASCADE"},
        "ordini": {
            (("cliente_id",), "clienti", ("id",)): "RESTRICT/RESTRICT",
            (("programma_fornitura_id",), "programmi_fornitura", ("id",)): "RESTRICT/RESTRICT",
            (("run_id",), "runs", ("id",)): "RESTRICT/RESTRICT",
        },
        "righe_ordine": {
            (("ordine_id",), "ordini", ("id",)): "RESTRICT/CASCADE",
            (("varieta_id",), "varieta", ("id",)): "RESTRICT/RESTRICT",
        },
        "origini_righe_ordine": {
            (("riga_ordine_id",), "righe_ordine", ("id",)): "RESTRICT/RESTRICT",
            (("riga_programma_id",), "righe_programma_fornitura", ("id",)): "RESTRICT/RESTRICT",
        },
        "audit_eventi": {(('run_id',), 'runs', ('id',)): "RESTRICT/RESTRICT"},
    }
    assert {table: _foreign_keys(inspector, table) for table in expected} == expected


def test_unique_e_indici_parziali(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    uniques = {
        table: {tuple(item["column_names"]) for item in inspector.get_unique_constraints(table, schema="tpo")}
        for table in ("clienti", "varieta", "programmi_fornitura",
                      "programmi_fornitura_versioni", "righe_programma_fornitura",
                      "ordini", "righe_ordine")
    }
    assert ("public_id",) in uniques["clienti"]
    assert ("public_id",) in uniques["varieta"]
    assert ("public_id",) in uniques["programmi_fornitura"]
    assert ("programma_fornitura_id", "numero_versione") in uniques["programmi_fornitura_versioni"]
    assert ("programma_versione_id", "posizione") in uniques["righe_programma_fornitura"]
    assert ("chiave_idempotenza",) in uniques["ordini"]
    assert ("ordine_id", "posizione") in uniques["righe_ordine"]
    assert inspector.get_pk_constraint("origini_righe_ordine", schema="tpo")["constrained_columns"] == ["riga_ordine_id", "riga_programma_id"]

    indexes = {item["name"]: item for item in inspector.get_indexes("programmi_fornitura_versioni", schema="tpo")}
    assert str(indexes["uq_programmi_fornitura_versioni_corrente"]["dialect_options"]["sqlite_where"]) == "valida_al IS NULL"
    assert str(indexes["uq_programmi_fornitura_versioni_cliente_attivo"]["dialect_options"]["sqlite_where"]) == "valida_al IS NULL AND stato = 'ATTIVO'"
    assert indexes["uq_programmi_fornitura_versioni_corrente"]["unique"] == 1
    assert indexes["uq_programmi_fornitura_versioni_cliente_attivo"]["unique"] == 1


def test_indici_sqlite_esatti_senza_duplicati(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    expected = {
        "clienti": {"ix_clienti_denominazione"},
        "varieta": {"ix_varieta_stato"},
        "programmi_fornitura": {"ix_programmi_fornitura_cliente_id"},
        "programmi_fornitura_versioni": {
            "uq_programmi_fornitura_versioni_corrente",
            "uq_programmi_fornitura_versioni_cliente_attivo",
            "ix_programmi_fornitura_versioni_programma_cliente",
            "ix_programmi_fornitura_versioni_stato_valida_al",
            "ix_programmi_fornitura_versioni_date",
        },
        "righe_programma_fornitura": {
            "ix_righe_programma_fornitura_varieta_id",
            "ix_righe_programma_fornitura_tipo_versione",
        },
        "righe_programma_giorni": {"ix_righe_programma_giorni_giorno_riga"},
        "ordini": {
            "ix_ordini_cliente_id", "ix_ordini_programma_fornitura_id",
            "ix_ordini_run_id", "ix_ordini_stato_data_consegna_prevista",
            "ix_ordini_cliente_data_ordine", "ix_ordini_programma_data_consegna",
        },
        "righe_ordine": {"ix_righe_ordine_varieta_id", "ix_righe_ordine_varieta_ordine"},
        "origini_righe_ordine": {"ix_origini_righe_ordine_riga_programma_id"},
        "audit_eventi": {
            "ix_audit_eventi_entity", "ix_audit_eventi_run_id",
            "ix_audit_eventi_actor", "ix_audit_eventi_occurred_at",
        },
    }
    actual = {
        table: {item["name"] for item in inspector.get_indexes(table, schema="tpo")}
        for table in expected
    }
    assert actual == expected


def test_locator_programma_versione_posizione_univoco(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    programma_public = inspector.get_unique_constraints("programmi_fornitura", schema="tpo")
    versione_unique = inspector.get_unique_constraints("programmi_fornitura_versioni", schema="tpo")
    riga_unique = inspector.get_unique_constraints("righe_programma_fornitura", schema="tpo")
    assert any(item["column_names"] == ["public_id"] for item in programma_public)
    assert any(item["column_names"] == ["programma_fornitura_id", "numero_versione"] for item in versione_unique)
    assert any(item["column_names"] == ["programma_versione_id", "posizione"] for item in riga_unique)


def test_colonne_esatte_tabelle_critiche(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    expected = {
        "programmi_fornitura_versioni": {"id", "programma_fornitura_id", "cliente_id", "numero_versione", "stato", "data_inizio", "data_fine", "orario_generazione", "finestra_operativa_giorni", "valida_dal", "valida_al", "created_at", "created_by"},
        "righe_programma_fornitura": {"id", "programma_versione_id", "posizione", "varieta_id", "quantita", "unita_misura", "tipo_ricorrenza", "intervallo_giorni"},
        "ordini": {"id", "public_id", "cliente_id", "programma_fornitura_id", "run_id", "data_ordine", "data_consegna_prevista", "stato", "tipo_creazione", "chiave_idempotenza", "created_at", "created_by"},
        "righe_ordine": {"id", "ordine_id", "posizione", "varieta_id", "quantita", "unita_misura"},
        "origini_righe_ordine": {"riga_ordine_id", "riga_programma_id"},
        "audit_eventi": {"id", "occurred_at", "actor", "run_id", "entity_type", "entity_public_id", "operation", "reason", "before_data", "after_data", "correlation_id"},
    }
    for table, columns in expected.items():
        assert {item["name"] for item in inspector.get_columns(table, schema="tpo")} == columns


def test_downgrade_0002_conserva_solo_foundation(tmp_path: Path) -> None:
    engine, connection = _database(tmp_path)
    try:
        config = make_config(connection=connection)
        command.upgrade(config, "head")
        command.downgrade(config, "20260804_0001")
        assert set(sa.inspect(connection).get_table_names(schema="tpo")) == FOUNDATION_TABLES
        command.downgrade(config, "base")
        assert sa.inspect(connection).get_table_names(schema="tpo") == []
    finally:
        connection.close()
        engine.dispose()


def test_downgrade_sicuro_senza_operazioni_distruttive_ampie() -> None:
    source = REVISION_PATH.read_text(encoding="utf-8")
    downgrade = source[source.index("def downgrade()") :]
    assert "CASCADE" not in downgrade.upper()
    assert "drop_all" not in downgrade
    assert "DropSchema" not in downgrade
    assert downgrade.index('op.drop_table("ordini"') < downgrade.index("reversed(ENUMS)")
    assert "ordine_creation_type" in source


def test_insieme_tabelle_0002_esatto(upgraded) -> None:
    tables = set(sa.inspect(upgraded).get_table_names(schema="tpo"))
    assert tables == FOUNDATION_TABLES | ORDER_COMMIT_TABLES
