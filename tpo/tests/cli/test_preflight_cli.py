from __future__ import annotations

from argparse import Namespace
from io import StringIO
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from googleapiclient.errors import HttpError

from src.tpo_core.bootstrap.factory import build_application
from src.tpo_core.bootstrap.settings import InvalidSettingsError
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.preflight import (
    PreflightDependencies,
    ReadOnlyGuardedGoogleService,
    ReadOnlyWriteAttemptError,
    run_preflight_command,
)
from src.tpo_core.infrastructure.google_sheets.errors import GoogleSheetsRepositoryError
from src.tpo_core.infrastructure.google_sheets.google_api_gateway import GoogleApiSheetsGateway
from src.tpo_core.infrastructure.google_sheets.mappers import ORDINI_HEADERS, PROGRAMMI_HEADERS


class FakeRequest:
    def __init__(self, response=None, error=None):
        self.response = response or {}
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.response


class FakeValuesResource:
    def __init__(self, service):
        self.service = service

    def get(self, **kwargs):
        self.service.read_calls.append(kwargs)
        sheet_name = kwargs["range"].split("!", 1)[0][1:-1].replace("''", "'")
        error = self.service.read_errors.get(sheet_name)
        return FakeRequest({"values": self.service.values.get(sheet_name, [])}, error)

    def append(self, **kwargs):
        self.service.append_calls.append(kwargs)
        return FakeRequest()


class FakeSpreadsheetsResource:
    def __init__(self, service):
        self.service = service

    def get(self, **kwargs):
        self.service.metadata_calls.append(kwargs)
        response = {
            "sheets": [
                {"properties": {"title": name}} for name in self.service.sheet_names
            ]
        }
        return FakeRequest(response, self.service.metadata_error)

    def values(self):
        return FakeValuesResource(self.service)


class FakeGoogleService:
    def __init__(self, *, values=None, sheet_names=None, metadata_error=None):
        self.values = values or {
            "PROGRAMMI_FORNITURA": [list(PROGRAMMI_HEADERS)],
            "ORDINI": [list(ORDINI_HEADERS)],
        }
        self.sheet_names = sheet_names or tuple(self.values)
        self.metadata_error = metadata_error
        self.read_errors = {}
        self.metadata_calls = []
        self.read_calls = []
        self.append_calls = []

    def spreadsheets(self):
        return FakeSpreadsheetsResource(self)


def cli_args(**overrides):
    values = {
        "settings": "settings.yaml",
        "current_system_date": "2026-08-03T13:00:00+01:00",
        "run_id": "RUN-000001",
        "json_output": False,
    }
    values.update(overrides)
    return Namespace(**values)


def write_settings(tmp_path: Path, *, credentials=True) -> tuple[Path, Path]:
    credentials_path = tmp_path / "service-account-local.json"
    if credentials:
        credentials_path.write_text("not-read-by-preflight", encoding="utf-8")
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        f"""google_sheets:
  spreadsheet_id: secret-spreadsheet-id
  credentials_file: {credentials_path}
  scopes:
    - scope
  sheets:
    - PROGRAMMI_FORNITURA
    - ORDINI
""",
        encoding="utf-8",
    )
    return settings_path, credentials_path


def execute(tmp_path: Path, *, service=None, args=None, credentials=True, dependencies=None):
    settings_path, credentials_path = write_settings(tmp_path, credentials=credentials)
    service = service or FakeGoogleService()
    calls = []

    def service_factory(path, *, scopes):
        calls.append((path, scopes))
        return service

    dependencies = dependencies or PreflightDependencies(
        service_factory=service_factory,
        application_factory=build_application,
    )
    command_args = args or cli_args()
    command_args.settings = str(settings_path)
    stdout, stderr = StringIO(), StringIO()
    code = run_preflight_command(
        command_args,
        stdout=stdout,
        stderr=stderr,
        dependencies=dependencies,
    )
    return code, stdout.getvalue(), stderr.getvalue(), service, calls, credentials_path


def programma_row():
    return [
        "PF-000001", "CLI-000001", "ATTIVO", "2026/08/03", "", "05:00",
        "3", "1", "VAR-000001", "10", "SET", "SETTIMANALE", "", "",
    ]


def ordine_row():
    return [
        "ORD-000001", "CLI-000001", "2026/08/03", "APERTO", "PF-000001",
        "2026/08/06", "key", "1", "VAR-000001", "10", "SET",
    ]


def test_parser_preflight_valido_e_json(monkeypatch) -> None:
    received = []
    monkeypatch.setattr(
        main_module,
        "run_preflight_command",
        lambda args, **kwargs: received.append(args) or 0,
    )
    code = main_module.main([
        "schedule", "preflight", "--settings", "s", "--current-system-date",
        "2026-08-03T13:00:00+01:00", "--run-id", "RUN-000001", "--json",
    ])
    assert code == 0
    assert received[0].json_output is True
    assert not hasattr(received[0], "simulate")


@pytest.mark.parametrize(
    "argv",
    [
        ["schedule", "preflight", "--current-system-date", "2026-08-03T13:00:00+01:00", "--run-id", "RUN-000001"],
        ["schedule", "preflight", "--settings", "s", "--run-id", "RUN-000001"],
        ["schedule", "preflight", "--settings", "s", "--current-system-date", "2026-08-03T13:00:00+01:00"],
        ["schedule", "preflight", "--settings", "s", "--current-system-date", "2026-08-03T13:00:00+01:00", "--run-id", "RUN-000001", "--write"],
        ["schedule", "unknown"],
    ],
)
def test_parser_preflight_rifiuta_argomenti_non_validi(monkeypatch, argv) -> None:
    monkeypatch.setattr(
        main_module,
        "run_preflight_command",
        lambda *args, **kwargs: pytest.fail("preflight non deve partire"),
    )
    assert main_module.main(argv) == 2


def test_successo_header_only_warning_nessuna_append(tmp_path) -> None:
    code, output, error, service, calls, _ = execute(tmp_path)
    assert code == 0
    assert error == ""
    assert len(calls) == 1
    assert service.append_calls == []
    assert "PREFLIGHT TOWER POWER OS" in output
    assert "SCHEDULING SIMULATION: OK" in output
    assert "nessun programma di fornitura presente" in output
    assert "ESITO PREFLIGHT: SUCCESS" in output
    assert "secret-spreadsheet-id" not in output


def test_successo_parsing_programma_e_ordine_reali(tmp_path) -> None:
    service = FakeGoogleService(values={
        "PROGRAMMI_FORNITURA": [list(PROGRAMMI_HEADERS), programma_row()],
        "ORDINI": [list(ORDINI_HEADERS), ordine_row()],
    })
    code, output, error, service, _, _ = execute(tmp_path, service=service)
    assert code == 0
    assert error == ""
    assert "PROGRAMMI LETTI: 1" in output
    assert "ORDINI ESISTENTI: 1" in output
    assert service.append_calls == []


def test_output_json_valido_e_senza_segreti(tmp_path) -> None:
    code, output, error, _, _, credentials_path = execute(
        tmp_path, args=cli_args(json_output=True)
    )
    assert code == 0
    assert error == ""
    payload = json.loads(output)
    assert payload["preflight"] is True
    assert payload["read_only"] is True
    assert payload["esito"] == "SUCCESS"
    assert payload["warnings"] == ["nessun programma di fornitura presente"]
    assert "secret-spreadsheet-id" not in output
    assert str(credentials_path) not in output
    assert "not-read-by-preflight" not in output


def test_credenziali_assenti_exit_4_senza_google(tmp_path) -> None:
    code, _, error, service, calls, _ = execute(tmp_path, credentials=False)
    assert code == 4
    assert "CREDENTIALS FILE" in error
    assert calls == []
    assert service.metadata_calls == []


def test_credenziali_directory_exit_4(tmp_path) -> None:
    settings_path, credentials_path = write_settings(tmp_path)
    credentials_path.unlink()
    credentials_path.mkdir()
    stdout, stderr = StringIO(), StringIO()
    code = run_preflight_command(
        cli_args(settings=str(settings_path)), stdout=stdout, stderr=stderr,
        dependencies=PreflightDependencies(service_factory=lambda *a, **k: pytest.fail("Google chiamato")),
    )
    assert code == 4
    assert "non è un file" in stderr.getvalue()


def test_credenziali_non_leggibili_exit_4(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(os, "access", lambda *args: False)
    code, _, error, _, calls, _ = execute(tmp_path)
    assert code == 4
    assert "non leggibile" in error
    assert calls == []


def test_servizio_non_costruibile_exit_4(tmp_path) -> None:
    settings_path, _ = write_settings(tmp_path)
    dependencies = PreflightDependencies(
        service_factory=lambda *a, **k: (_ for _ in ()).throw(GoogleSheetsRepositoryError("auth"))
    )
    stdout, stderr = StringIO(), StringIO()
    code = run_preflight_command(
        cli_args(settings=str(settings_path)), stdout=stdout, stderr=stderr,
        dependencies=dependencies,
    )
    assert code == 4
    assert "GOOGLE SERVICE" in stderr.getvalue()


def test_spreadsheet_non_accessibile_exit_5_e_id_mascherato(tmp_path) -> None:
    error = HttpError(SimpleNamespace(status=403, reason="forbidden"), b'{"error":{"message":"private"}}')
    service = FakeGoogleService(metadata_error=error)
    code, _, message, _, _, _ = execute(tmp_path, service=service)
    assert code == 5
    assert "SPREADSHEET ACCESS" in message
    assert "secret-spreadsheet-id" not in message
    assert "se***id" in message


@pytest.mark.parametrize("names", [("ORDINI",), ("PROGRAMMI_FORNITURA",)])
def test_foglio_mancante_exit_6(tmp_path, names) -> None:
    service = FakeGoogleService(sheet_names=names)
    code, _, error, _, _, _ = execute(tmp_path, service=service)
    assert code == 6
    assert "SHEET" in error


@pytest.mark.parametrize(
    "headers",
    [
        PROGRAMMI_HEADERS[:-1],
        PROGRAMMI_HEADERS + ("EXTRA",),
        (PROGRAMMI_HEADERS[1], PROGRAMMI_HEADERS[0], *PROGRAMMI_HEADERS[2:]),
        ("", *PROGRAMMI_HEADERS[1:]),
        (PROGRAMMI_HEADERS[0], PROGRAMMI_HEADERS[0], *PROGRAMMI_HEADERS[2:]),
    ],
)
def test_schema_programmi_non_valido_exit_7(tmp_path, headers) -> None:
    service = FakeGoogleService(values={
        "PROGRAMMI_FORNITURA": [list(headers)],
        "ORDINI": [list(ORDINI_HEADERS)],
    })
    code, _, error, _, _, _ = execute(tmp_path, service=service)
    assert code == 7
    assert "SCHEMA" in error


def test_riga_programma_invalida_exit_8_senza_correzione(tmp_path) -> None:
    invalid = programma_row()
    invalid[9] = "10,5"
    service = FakeGoogleService(values={
        "PROGRAMMI_FORNITURA": [list(PROGRAMMI_HEADERS), invalid],
        "ORDINI": [list(ORDINI_HEADERS)],
    })
    code, _, error, service, _, _ = execute(tmp_path, service=service)
    assert code == 8
    assert "PARSING" in error
    assert invalid[9] == "10,5"
    assert service.append_calls == []


def test_riga_ordine_invalida_exit_8(tmp_path) -> None:
    invalid = ordine_row()
    invalid[0] = "bad"
    service = FakeGoogleService(values={
        "PROGRAMMI_FORNITURA": [list(PROGRAMMI_HEADERS)],
        "ORDINI": [list(ORDINI_HEADERS), invalid],
    })
    code, _, error, _, _, _ = execute(tmp_path, service=service)
    assert code == 8
    assert "PARSING" in error


class EmptyRepository:
    def list_for_scheduling(self):
        return ()

    def list_scheduled_orders(self):
        return ()


class FailingUseCase:
    def __init__(self, error):
        self.error = error

    def execute(self, **kwargs):
        raise self.error


class FakeApplicationContainer:
    def __init__(self, use_case):
        self.programmi_repository = EmptyRepository()
        self.ordini_repository = EmptyRepository()
        self.run_scheduling = use_case


def test_simulazione_fallita_exit_9(tmp_path) -> None:
    service = FakeGoogleService()
    dependencies = PreflightDependencies(
        service_factory=lambda *args, **kwargs: service,
        application_factory=lambda *args, **kwargs: FakeApplicationContainer(
            FailingUseCase(GoogleSheetsRepositoryError("scheduling failed"))
        ),
    )
    code, _, error, _, _, _ = execute(tmp_path, dependencies=dependencies)
    assert code == 9
    assert "SCHEDULING SIMULATION" in error


def test_tentativo_scrittura_durante_simulazione_exit_10(tmp_path) -> None:
    service = FakeGoogleService()

    class WritingUseCase:
        def __init__(self, google_service):
            self.google_service = google_service

        def execute(self, **kwargs):
            self.google_service.spreadsheets().values().append().execute()

    dependencies = PreflightDependencies(
        service_factory=lambda *args, **kwargs: service,
        application_factory=lambda *args, google_service, **kwargs: (
            FakeApplicationContainer(WritingUseCase(google_service))
        ),
    )
    code, _, error, service, _, _ = execute(tmp_path, dependencies=dependencies)
    assert code == 10
    assert "READ ONLY" in error
    assert service.append_calls == []


def test_guardia_consente_lettura_e_blocca_append() -> None:
    service = FakeGoogleService()
    guarded = ReadOnlyGuardedGoogleService(service)
    gateway = GoogleApiSheetsGateway(guarded)
    assert gateway.read_rows(
        spreadsheet_id="id", sheet_name="ORDINI"
    ) == ()
    with pytest.raises(ReadOnlyWriteAttemptError):
        gateway.append_rows(
            spreadsheet_id="id",
            sheet_name="ORDINI",
            rows=(dict(zip(ORDINI_HEADERS, ("",) * len(ORDINI_HEADERS))),),
        )
    assert service.append_calls == []


def test_argomenti_invalidi_exit_2_prima_delle_settings(tmp_path) -> None:
    dependencies = PreflightDependencies(
        settings_loader=lambda path: pytest.fail("settings caricate")
    )
    stdout, stderr = StringIO(), StringIO()
    code = run_preflight_command(
        cli_args(run_id="bad"), stdout=stdout, stderr=stderr,
        dependencies=dependencies,
    )
    assert code == 2
    assert "ARGUMENTS" in stderr.getvalue()


def test_settings_invalid_exit_3(tmp_path) -> None:
    dependencies = PreflightDependencies(
        settings_loader=lambda path: (_ for _ in ()).throw(InvalidSettingsError("bad"))
    )
    stdout, stderr = StringIO(), StringIO()
    code = run_preflight_command(
        cli_args(), stdout=stdout, stderr=stderr, dependencies=dependencies
    )
    assert code == 3
    assert "SETTINGS" in stderr.getvalue()


def test_preflight_non_usa_clock_reale_o_singleton() -> None:
    import src.tpo_core.cli.preflight as module

    names = set(module.__dict__)
    assert "datetime" not in names
    assert "date" not in names
    assert "time" not in names
    assert not hasattr(module, "container")
