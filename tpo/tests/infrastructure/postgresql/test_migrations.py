from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa

from src.tpo_core.infrastructure.postgresql import alembic as migration_runner
from src.tpo_core.infrastructure.postgresql.alembic import METADATA, make_config, migration_url
from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings

FOUNDATION_TABLES = {"id_sequences", "runs", "run_messaggi", "run_log"}
ORDER_COMMIT_TABLES = {
    "clienti",
    "varieta",
    "programmi_fornitura",
    "programmi_fornitura_versioni",
    "righe_programma_fornitura",
    "righe_programma_giorni",
    "ordini",
    "righe_ordine",
    "origini_righe_ordine",
    "audit_eventi",
}
PREREQUISITE_TABLES = {
    "cultivar", "usi_produttivi", "cultivar_usi", "protocolli",
    "protocollo_versioni", "sementi", "semente_impieghi", "lotti_seme",
    "semine", "raccolte", "consegne", "stock", "movimenti_magazzino",
}
EXPECTED_TABLES = FOUNDATION_TABLES | ORDER_COMMIT_TABLES | PREREQUISITE_TABLES


def _temporary_database(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'main.sqlite'}")
    connection = engine.connect()
    connection.connection.driver_connection.create_function("btrim", 1, str.strip)
    schema_path = str(tmp_path / "tpo.sqlite").replace("'", "''")
    connection.exec_driver_sql(f"ATTACH DATABASE '{schema_path}' AS tpo")
    return engine, connection


def test_upgrade_crea_solamente_le_tabelle_congelate(tmp_path: Path) -> None:
    engine, connection = _temporary_database(tmp_path)
    try:
        command.upgrade(make_config(connection=connection), "head")
        tables = set(sa.inspect(connection).get_table_names(schema="tpo"))
        assert tables == EXPECTED_TABLES
    finally:
        connection.close()
        engine.dispose()


def test_downgrade_rimuove_tutte_le_tabelle(tmp_path: Path) -> None:
    engine, connection = _temporary_database(tmp_path)
    try:
        config = make_config(connection=connection)
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        assert sa.inspect(connection).get_table_names(schema="tpo") == []
    finally:
        connection.close()
        engine.dispose()


def test_metadata_contiene_colonne_e_tipi_congelati() -> None:
    assert {table.name for table in METADATA.tables.values()} == FOUNDATION_TABLES
    assert set(METADATA.tables["tpo.id_sequences"].c.keys()) == {
        "sequence_name", "identifier_type", "prefix", "next_value", "version", "updated_at", "updated_by"
    }
    assert set(METADATA.tables["tpo.runs"].c.keys()) == {
        "id", "public_id", "started_at", "completed_at", "simulation", "state",
        "programmi_letti", "righe_valutate", "occorrenze_valutate", "ordini_generati",
        "elementi_saltati", "version", "created_by",
    }
    assert set(METADATA.tables["tpo.run_messaggi"].c.keys()) == {
        "id", "run_id", "tipo", "posizione", "messaggio", "created_at"
    }
    assert set(METADATA.tables["tpo.run_log"].c.keys()) == {
        "id", "run_id", "occurred_at", "level", "event_type", "message", "context"
    }


def test_migration_non_contiene_tabelle_vietate() -> None:
    forbidden = {
        "clienti", "ordini", "programmi", "semine", "raccolti", "stock", "movimenti"
    }
    assert FOUNDATION_TABLES.isdisjoint(forbidden)


def test_revision_chain_valida_e_lineare() -> None:
    revisions = list(ScriptDirectory.from_config(make_config()).walk_revisions())
    assert [revision.revision for revision in revisions] == [
        "20260810_0004",
        "20260810_0003",
        "20260806_0002",
        "20260804_0001",
    ]
    assert revisions[0].down_revision == "20260810_0003"
    assert revisions[1].down_revision == "20260806_0002"
    assert revisions[2].down_revision == "20260804_0001"
    assert revisions[3].down_revision is None


def test_migration_url_non_espone_password() -> None:
    settings = PostgreSQLSettings(
        "db.example.invalid", 5432, "towerpower", "app", "secret", "require", 3
    )
    url = migration_url(settings)
    assert url.password == "secret"
    assert "secret" not in str(url)
    assert "secret" not in repr(url)


class FakeConnectionContext:
    def __init__(self, connection: object) -> None:
        self.connection = connection

    def __enter__(self) -> object:
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


class FakeEngine:
    def __init__(self, *, connect_error: Exception | None = None) -> None:
        self.connect_error = connect_error
        self.connect_calls = 0
        self.dispose_calls = 0
        self.connection = object()

    def connect(self) -> FakeConnectionContext:
        self.connect_calls += 1
        if self.connect_error is not None:
            raise self.connect_error
        return FakeConnectionContext(self.connection)

    def dispose(self) -> None:
        self.dispose_calls += 1


def _migration_settings() -> PostgreSQLSettings:
    return PostgreSQLSettings(
        "db.example.invalid", 5432, "towerpower", "app", "secret", "require", 3
    )


def test_upgrade_riuscito_esegue_dispose(monkeypatch) -> None:
    engine = FakeEngine()
    upgrade_calls = []
    monkeypatch.setattr(migration_runner.sa, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(
        migration_runner.command,
        "upgrade",
        lambda config, revision: upgrade_calls.append((config, revision)),
    )

    migration_runner.upgrade(_migration_settings())

    assert engine.connect_calls == 1
    assert engine.dispose_calls == 1
    assert len(upgrade_calls) == 1
    assert upgrade_calls[0][1] == "head"


def test_connect_error_esegue_dispose_propaga_causa_e_non_riprova(monkeypatch) -> None:
    error = TypeError("safe connect failure")
    engine = FakeEngine(connect_error=error)
    monkeypatch.setattr(migration_runner.sa, "create_engine", lambda *args, **kwargs: engine)

    with pytest.raises(TypeError) as captured:
        migration_runner.upgrade(_migration_settings())

    assert captured.value is error
    assert "secret" not in str(captured.value)
    assert engine.connect_calls == 1
    assert engine.dispose_calls == 1


def test_alembic_error_esegue_dispose_propaga_causa_e_non_riprova(monkeypatch) -> None:
    error = RuntimeError("safe upgrade failure")
    engine = FakeEngine()
    upgrade_calls = 0

    def failed_upgrade(config, revision):
        nonlocal upgrade_calls
        upgrade_calls += 1
        raise error

    monkeypatch.setattr(migration_runner.sa, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(migration_runner.command, "upgrade", failed_upgrade)

    with pytest.raises(RuntimeError) as captured:
        migration_runner.upgrade(_migration_settings())

    assert captured.value is error
    assert "secret" not in str(captured.value)
    assert engine.connect_calls == 1
    assert upgrade_calls == 1
    assert engine.dispose_calls == 1


def test_downgrade_e_conservativo_e_ordinato() -> None:
    revision_path = (
        Path(__file__).parents[3]
        / "migrations"
        / "versions"
        / "20260804_0001_postgresql_foundation.py"
    )
    source = revision_path.read_text(encoding="utf-8")
    downgrade = source[source.index("def downgrade()") :]

    last_table = max(downgrade.index(f'op.drop_table("{name}"') for name in FOUNDATION_TABLES)
    first_enum = min(downgrade.index(f"{name}.drop(") for name in (
        "run_log_level", "run_message_type", "run_state"
    ))
    schema_drop = downgrade.index("sa.schema.DropSchema(SCHEMA)")

    assert last_table < first_enum < schema_drop
    assert "CASCADE" not in downgrade.upper()
    assert "drop_all" not in downgrade
    assert "DropSchema(SCHEMA," not in downgrade
