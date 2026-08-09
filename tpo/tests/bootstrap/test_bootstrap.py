from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from src.tpo_core.application.committer import ApplicationCommitter
from src.tpo_core.application.operational_scheduling import (
    ExecuteSchedulingCommit,
    OperationalSchedulingOrchestrator,
)
from src.tpo_core.application.scheduling.engine import SchedulingEngine
from src.tpo_core.application.scheduling.use_case import RunScheduling
from src.tpo_core.bootstrap.container import ApplicationContainer
from src.tpo_core.bootstrap.factory import build_application
from src.tpo_core.bootstrap.settings import InvalidSettingsError, load_settings
from src.tpo_core.infrastructure.google_sheets.google_api_gateway import (
    GoogleApiSheetsGateway,
)
from src.tpo_core.infrastructure.google_sheets.ordini_repository import (
    GoogleSheetsOrdineRepository,
)
from src.tpo_core.infrastructure.google_sheets.programmi_repository import (
    GoogleSheetsProgrammaFornituraRepository,
)
from src.tpo_core.infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from src.tpo_core.infrastructure.postgresql.commit_repository import (
    PostgreSQLCommitRepository,
)
from src.tpo_core.infrastructure.postgresql.health import PostgreSQLHealthCheck
from src.tpo_core.infrastructure.postgresql.orders_repository import PostgreSQLOrdineRepository
from src.tpo_core.infrastructure.postgresql.programmi_repository import (
    PostgreSQLVersionedProgrammaFornituraRepository,
)
from src.tpo_core.infrastructure.postgresql.write_plan_validation_repository import (
    PostgreSQLWritePlanValidationRepository,
)


class NoNetworkGoogleService:
    def __init__(self) -> None:
        self.calls = 0

    def spreadsheets(self):
        self.calls += 1
        raise AssertionError("Il bootstrap non deve accedere alla rete.")


class FakeIdGenerator:
    def next_id(self, identifier_type):
        raise AssertionError("Il bootstrap non deve generare identificativi.")


class NoCallClock:
    def now(self):
        raise AssertionError("Il bootstrap non deve leggere il clock.")


@pytest.fixture
def settings_file(tmp_path: Path) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(
        """google_sheets:
  spreadsheet_id: spreadsheet-test
  credentials_file: credentials.json
  scopes:
    - https://www.googleapis.com/auth/spreadsheets
  sheets:
    - PROGRAMMI_FORNITURA
    - ORDINI
""",
        encoding="utf-8",
    )
    return path


def build(settings_file: Path):
    service = NoNetworkGoogleService()
    generator = FakeIdGenerator()
    container = build_application(
        settings_file,
        google_service=service,
        id_generator=generator,
    )
    return container, service, generator


def test_costruzione_completa(settings_file: Path) -> None:
    container, _, _ = build(settings_file)
    assert isinstance(container, ApplicationContainer)
    assert isinstance(container.google_gateway, GoogleApiSheetsGateway)
    assert isinstance(
        container.programmi_repository, GoogleSheetsProgrammaFornituraRepository
    )
    assert isinstance(container.ordini_repository, GoogleSheetsOrdineRepository)
    assert isinstance(container.scheduling_engine, SchedulingEngine)
    assert isinstance(container.run_scheduling, RunScheduling)
    assert container.settings.credentials_file == "credentials.json"
    assert container.settings.scopes == (
        "https://www.googleapis.com/auth/spreadsheets",
    )


def test_dipendenze_collegate_alle_stesse_istanze(settings_file: Path) -> None:
    container, service, generator = build(settings_file)
    assert container.google_gateway._service is service
    assert container.programmi_repository._gateway is container.google_gateway
    assert container.ordini_repository._gateway is container.google_gateway
    assert container.run_scheduling._programmi_repository is container.programmi_repository
    assert container.run_scheduling._ordini_repository is container.ordini_repository
    assert container.run_scheduling._scheduling_engine is container.scheduling_engine
    assert container.run_scheduling._id_generator is generator


def test_build_non_accede_alla_rete(settings_file: Path) -> None:
    _, service, _ = build(settings_file)
    assert service.calls == 0


def test_build_postgresql_pigro_da_environment_esplicito(settings_file: Path) -> None:
    environment = {
        "TPO_DATABASE_HOST": "db.example.invalid",
        "TPO_DATABASE_PORT": "5432",
        "TPO_DATABASE_NAME": "towerpower",
        "TPO_DATABASE_USER": "app",
        "TPO_DATABASE_PASSWORD": "secret",
        "TPO_DATABASE_SSLMODE": "require",
        "TPO_DATABASE_CONNECT_TIMEOUT": "3",
    }
    service = NoNetworkGoogleService()
    clock = NoCallClock()
    container = build_application(
        settings_file,
        google_service=service,
        id_generator=FakeIdGenerator(),
        postgresql_environment=environment,
        clock=clock,
    )
    assert container.postgresql_settings.database == "towerpower"
    assert isinstance(container.postgresql_connection_factory, PostgreSQLConnectionFactory)
    assert isinstance(container.postgresql_health_check, PostgreSQLHealthCheck)
    assert isinstance(
        container.postgresql_commit_repository,
        PostgreSQLCommitRepository,
    )
    assert (
        container.postgresql_commit_repository._connection_factory
        is container.postgresql_connection_factory
    )
    assert isinstance(container.application_committer, ApplicationCommitter)
    assert isinstance(
        container.operational_scheduling_orchestrator,
        OperationalSchedulingOrchestrator,
    )
    execute_scheduling_commit = (
        container.operational_scheduling_orchestrator._execute_scheduling_commit
    )
    assert isinstance(execute_scheduling_commit, ExecuteSchedulingCommit)
    assert container.clock is clock
    assert container.postgresql_commit_repository._clock is clock
    assert execute_scheduling_commit._clock is clock
    assert container.operational_scheduling_orchestrator._clock is clock
    assert (
        not hasattr(execute_scheduling_commit, "_run_scheduling")
    )
    assert (
        container.operational_scheduling_orchestrator._id_allocator
        is container.operational_scheduling_orchestrator._run_service._id_allocator
    )
    assert (
        container.application_committer._repository
        is container.postgresql_commit_repository
    )
    assert (
        execute_scheduling_commit._committer
        is container.application_committer
    )
    operational = container.operational_scheduling_orchestrator._run_scheduling
    assert isinstance(
        operational._programmi_repository,
        PostgreSQLVersionedProgrammaFornituraRepository,
    )
    assert isinstance(operational._ordini_repository, PostgreSQLOrdineRepository)
    assert (
        operational._programmi_repository._connection_factory
        is container.postgresql_connection_factory
    )
    assert (
        execute_scheduling_commit
        ._write_plan_validator
        ._repository
        ._connection_factory
        is container.postgresql_connection_factory
    )
    assert isinstance(
        execute_scheduling_commit._write_plan_validator._repository,
        PostgreSQLWritePlanValidationRepository,
    )
    assert not any(
        isinstance(value, GoogleSheetsOrdineRepository)
        for value in vars(execute_scheduling_commit).values()
    )
    assert service.calls == 0


def test_build_postgresql_non_apre_connessioni(
    settings_file: Path,
    monkeypatch,
) -> None:
    connect_calls = []

    def forbidden_connect(factory):
        connect_calls.append(factory)
        raise AssertionError("Il bootstrap PostgreSQL deve restare lazy.")

    monkeypatch.setattr(PostgreSQLConnectionFactory, "connect", forbidden_connect)
    environment = {
        "TPO_DATABASE_HOST": "db.example.invalid",
        "TPO_DATABASE_PORT": "5432",
        "TPO_DATABASE_NAME": "towerpower",
        "TPO_DATABASE_USER": "app",
        "TPO_DATABASE_PASSWORD": "secret",
        "TPO_DATABASE_SSLMODE": "require",
        "TPO_DATABASE_CONNECT_TIMEOUT": "3",
    }

    container = build_application(
        settings_file,
        google_service=NoNetworkGoogleService(),
        id_generator=FakeIdGenerator(),
        postgresql_environment=environment,
    )

    assert isinstance(container.postgresql_commit_repository, PostgreSQLCommitRepository)
    assert isinstance(container.application_committer, ApplicationCommitter)
    assert isinstance(
        container.operational_scheduling_orchestrator,
        OperationalSchedulingOrchestrator,
    )
    assert connect_calls == []


def test_runtime_senza_postgresql_non_costruisce_commit_repository(
    settings_file: Path,
) -> None:
    container, _, _ = build(settings_file)
    assert container.postgresql_settings is None
    assert container.postgresql_connection_factory is None
    assert container.postgresql_commit_repository is None
    assert container.application_committer is None
    assert container.operational_scheduling_orchestrator is None
    assert isinstance(container.run_scheduling, RunScheduling)


def test_build_non_legge_env_local(settings_file: Path, monkeypatch) -> None:
    original_read_text = Path.read_text
    paths = []

    def tracked_read_text(path, *args, **kwargs):
        paths.append(path)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracked_read_text)
    build(settings_file)
    assert all(path.name != ".env.local" for path in paths)


def test_core_non_dipende_da_psycopg_o_supabase() -> None:
    source_root = Path(__file__).parents[2] / "src" / "tpo_core"
    for area in ("domain", "application"):
        for path in (source_root / area).rglob("*.py"):
            source = path.read_text(encoding="utf-8").lower()
            assert "psycopg" not in source
            assert "supabase" not in source


def test_build_ripetibile_senza_singleton(settings_file: Path) -> None:
    first, _, _ = build(settings_file)
    second, _, _ = build(settings_file)
    assert first is not second
    assert first.google_gateway is not second.google_gateway
    assert first.programmi_repository is not second.programmi_repository
    assert first.ordini_repository is not second.ordini_repository
    assert first.scheduling_engine is not second.scheduling_engine
    assert first.run_scheduling is not second.run_scheduling
    assert first.operational_scheduling_orchestrator is None
    assert second.operational_scheduling_orchestrator is None


@pytest.mark.parametrize(
    "content",
    [
        "",
        "[]",
        "google_sheets: {}",
        "google_sheets:\n  spreadsheet_id: ''\n  credentials_file: c\n  scopes: [s]\n  sheets: [PROGRAMMI_FORNITURA, ORDINI]",
        "google_sheets:\n  spreadsheet_id: id\n  credentials_file: c\n  scopes: [s]\n  sheets: [ORDINI]",
        "google_sheets:\n  spreadsheet_id: id\n  credentials_file: c\n  scopes: [s]\n  sheets: [PROGRAMMI_FORNITURA]",
        "google_sheets:\n  spreadsheet_id: id\n  credentials_file: c\n  scopes: [s]\n  sheets: [PROGRAMMI_FORNITURA, ORDINI, ORDINI]",
        "google_sheets:\n  spreadsheet_id: id\n  scopes: [s]\n  sheets: [PROGRAMMI_FORNITURA, ORDINI]",
        "google_sheets:\n  spreadsheet_id: id\n  credentials_file: c\n  scopes: []\n  sheets: [PROGRAMMI_FORNITURA, ORDINI]",
    ],
)
def test_configurazione_non_valida(content: str, tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(InvalidSettingsError):
        load_settings(path)


def test_file_configurazione_assente_rifiutato(tmp_path: Path) -> None:
    with pytest.raises(InvalidSettingsError):
        load_settings(tmp_path / "missing.yaml")


def test_gateway_non_costruito_prima_del_bootstrap(monkeypatch) -> None:
    module = importlib.import_module("src.tpo_core.bootstrap.factory")
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("costruzione inattesa")

    monkeypatch.setattr(module, "_build_container", forbidden)
    importlib.reload(importlib.import_module("src.tpo_core.bootstrap.settings"))
    assert calls == []


def test_import_privo_di_side_effect(monkeypatch) -> None:
    gateway_module = importlib.import_module(
        "src.tpo_core.infrastructure.google_sheets.google_api_gateway"
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("autenticazione inattesa durante import")

    monkeypatch.setattr(gateway_module, "build_google_sheets_service", forbidden)
    importlib.reload(importlib.import_module("src.tpo_core.bootstrap.container"))
    importlib.reload(importlib.import_module("src.tpo_core.bootstrap.factory"))


def test_factory_espone_una_sola_funzione_pubblica() -> None:
    module = importlib.import_module("src.tpo_core.bootstrap.factory")
    public_functions = {
        name
        for name, value in vars(module).items()
        if not name.startswith("_") and callable(value) and getattr(value, "__module__", None) == module.__name__
    }
    assert public_functions == {"build_application"}
