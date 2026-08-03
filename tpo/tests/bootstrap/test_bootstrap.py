from __future__ import annotations

import importlib
from pathlib import Path

import pytest

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


class NoNetworkGoogleService:
    def __init__(self) -> None:
        self.calls = 0

    def spreadsheets(self):
        self.calls += 1
        raise AssertionError("Il bootstrap non deve accedere alla rete.")


class FakeIdGenerator:
    def next_id(self, identifier_type):
        raise AssertionError("Il bootstrap non deve generare identificativi.")


@pytest.fixture
def settings_file(tmp_path: Path) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(
        """google_sheets:
  spreadsheet_id: spreadsheet-test
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


def test_build_ripetibile_senza_singleton(settings_file: Path) -> None:
    first, _, _ = build(settings_file)
    second, _, _ = build(settings_file)
    assert first is not second
    assert first.google_gateway is not second.google_gateway
    assert first.programmi_repository is not second.programmi_repository
    assert first.ordini_repository is not second.ordini_repository
    assert first.scheduling_engine is not second.scheduling_engine
    assert first.run_scheduling is not second.run_scheduling


@pytest.mark.parametrize(
    "content",
    [
        "",
        "[]",
        "google_sheets: {}",
        "google_sheets:\n  spreadsheet_id: ''\n  sheets: [PROGRAMMI_FORNITURA, ORDINI]",
        "google_sheets:\n  spreadsheet_id: id\n  sheets: [ORDINI]",
        "google_sheets:\n  spreadsheet_id: id\n  sheets: [PROGRAMMI_FORNITURA]",
        "google_sheets:\n  spreadsheet_id: id\n  sheets: [PROGRAMMI_FORNITURA, ORDINI, ORDINI]",
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
