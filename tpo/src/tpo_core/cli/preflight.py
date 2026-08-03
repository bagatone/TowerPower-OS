"""Preflight end-to-end irrevocabilmente read-only per Google Sheets."""

from __future__ import annotations

import json
import os
from argparse import Namespace
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, TextIO

from ..bootstrap.factory import build_application
from ..bootstrap.settings import ApplicationSettings, InvalidSettingsError, load_settings
from ..domain.errors import DomainError, InvalidTimeReferenceError
from ..domain.identifiers import InvalidIdentifierError, RunId
from ..infrastructure.google_sheets.errors import (
    GoogleSheetsRepositoryError,
    InvalidSheetRowError,
    InvalidSheetSchemaError,
)
from ..infrastructure.google_sheets.google_api_gateway import (
    GoogleApiSheetsGateway,
    build_google_sheets_service,
)
from ..infrastructure.google_sheets.mappers import ORDINI_HEADERS, PROGRAMMI_HEADERS
from .scheduling import SimulationOnlyIdGenerator, _parse_current_system_date


class ReadOnlyWriteAttemptError(GoogleSheetsRepositoryError):
    """Tentativo di scrittura bloccato dal preflight."""


class ReadOnlyGuardedGoogleService:
    """Proxy del client Google che consente letture e blocca sempre append."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def spreadsheets(self):
        return _ReadOnlySpreadsheetsResource(self._service.spreadsheets())


class _ReadOnlySpreadsheetsResource:
    def __init__(self, resource: Any) -> None:
        self._resource = resource

    def get(self, **kwargs):
        return self._resource.get(**kwargs)

    def values(self):
        return _ReadOnlyValuesResource(self._resource.values())


class _ReadOnlyValuesResource:
    def __init__(self, resource: Any) -> None:
        self._resource = resource

    def get(self, **kwargs):
        return self._resource.get(**kwargs)

    def append(self, **kwargs):
        raise ReadOnlyWriteAttemptError(
            "Tentativo di scrittura bloccato dalla guardia read-only."
        )


@dataclass(frozen=True)
class PreflightResult:
    settings_ok: bool
    credentials_file_ok: bool
    google_service_ok: bool
    spreadsheet_access_ok: bool
    programmi_sheet_ok: bool
    ordini_sheet_ok: bool
    programmi_schema_ok: bool
    ordini_schema_ok: bool
    programmi_parse_ok: bool
    ordini_parse_ok: bool
    scheduling_simulation_ok: bool
    programmi_letti: int
    ordini_esistenti: int
    anteprime_generate: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PreflightDependencies:
    settings_loader: Callable[[str | Path], ApplicationSettings] = load_settings
    service_factory: Callable[..., Any] = build_google_sheets_service
    gateway_factory: Callable[[Any], GoogleApiSheetsGateway] = GoogleApiSheetsGateway
    application_factory: Callable[..., Any] = build_application


def run_preflight_command(
    args: Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
    dependencies: PreflightDependencies | None = None,
) -> int:
    dependencies = dependencies or PreflightDependencies()
    try:
        run_id = RunId(args.run_id)
        current_system_date = _parse_current_system_date(args.current_system_date)
    except (InvalidIdentifierError, InvalidTimeReferenceError, ValueError) as exc:
        return _fail("ARGUMENTS", str(exc), 2, stderr)

    try:
        settings = dependencies.settings_loader(args.settings)
    except InvalidSettingsError as exc:
        return _fail("SETTINGS", str(exc), 3, stderr)

    credentials_path = Path(settings.credentials_file)
    if not credentials_path.exists():
        return _fail("CREDENTIALS FILE", "file non presente", 4, stderr)
    if not credentials_path.is_file():
        return _fail("CREDENTIALS FILE", "il percorso non è un file", 4, stderr)
    if not os.access(credentials_path, os.R_OK):
        return _fail("CREDENTIALS FILE", "file non leggibile", 4, stderr)

    try:
        service = dependencies.service_factory(
            settings.credentials_file, scopes=settings.scopes
        )
    except GoogleSheetsRepositoryError as exc:
        return _fail("GOOGLE SERVICE", str(exc), 4, stderr)

    guarded_service = ReadOnlyGuardedGoogleService(service)
    gateway = dependencies.gateway_factory(guarded_service)
    try:
        sheet_names = gateway.list_sheet_names(spreadsheet_id=settings.spreadsheet_id)
    except GoogleSheetsRepositoryError as exc:
        return _fail("SPREADSHEET ACCESS", str(exc), 5, stderr)

    missing = [
        name
        for name in (settings.programmi_fornitura_sheet, settings.ordini_sheet)
        if name not in sheet_names
    ]
    if missing:
        return _fail("SHEET", f"foglio mancante: {missing[0]}", 6, stderr)

    try:
        programmi_headers = gateway.read_headers(
            spreadsheet_id=settings.spreadsheet_id,
            sheet_name=settings.programmi_fornitura_sheet,
        )
        if programmi_headers != PROGRAMMI_HEADERS:
            raise InvalidSheetSchemaError(
                "PROGRAMMI_FORNITURA: intestazioni fisiche non conformi."
            )
        ordini_headers = gateway.read_headers(
            spreadsheet_id=settings.spreadsheet_id,
            sheet_name=settings.ordini_sheet,
        )
        if ordini_headers != ORDINI_HEADERS:
            raise InvalidSheetSchemaError("ORDINI: intestazioni fisiche non conformi.")
    except (InvalidSheetSchemaError, GoogleSheetsRepositoryError) as exc:
        return _fail("SCHEMA", str(exc), 7, stderr)

    try:
        container = dependencies.application_factory(
            args.settings,
            google_service=guarded_service,
            id_generator=SimulationOnlyIdGenerator(),
        )
        programmi = container.programmi_repository.list_for_scheduling()
        ordini = container.ordini_repository.list_scheduled_orders()
    except ReadOnlyWriteAttemptError as exc:
        return _fail("READ ONLY", str(exc), 10, stderr)
    except InvalidSettingsError as exc:
        return _fail("SETTINGS", str(exc), 3, stderr)
    except (InvalidSheetRowError, InvalidSheetSchemaError, DomainError) as exc:
        return _fail("PARSING", str(exc), 8, stderr)
    except GoogleSheetsRepositoryError as exc:
        return _fail("PARSING", str(exc), 8, stderr)

    warnings = () if programmi else ("nessun programma di fornitura presente",)
    try:
        scheduling = container.run_scheduling.execute(
            run_id=run_id,
            current_system_date=current_system_date,
            simulation=True,
        )
    except ReadOnlyWriteAttemptError as exc:
        return _fail("READ ONLY", str(exc), 10, stderr)
    except (GoogleSheetsRepositoryError, DomainError) as exc:
        return _fail("SCHEDULING SIMULATION", str(exc), 9, stderr)

    result = PreflightResult(
        settings_ok=True,
        credentials_file_ok=True,
        google_service_ok=True,
        spreadsheet_access_ok=True,
        programmi_sheet_ok=True,
        ordini_sheet_ok=True,
        programmi_schema_ok=True,
        ordini_schema_ok=True,
        programmi_parse_ok=True,
        ordini_parse_ok=True,
        scheduling_simulation_ok=True,
        programmi_letti=len(programmi),
        ordini_esistenti=len(ordini),
        anteprime_generate=len(scheduling.anteprime),
        warnings=warnings,
    )
    if args.json_output:
        print(json.dumps(_payload(result), ensure_ascii=True, separators=(",", ":")), file=stdout)
    else:
        print(_format_text(result), file=stdout)
    return 0


def _fail(gate: str, message: str, code: int, stderr: TextIO) -> int:
    print(f"PREFLIGHT FALLITO [{gate}]: {message}", file=stderr)
    return code


def _payload(result: PreflightResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["warnings"] = list(result.warnings)
    return {"preflight": True, "read_only": True, **payload, "esito": "SUCCESS"}


def _format_text(result: PreflightResult) -> str:
    checks = (
        ("SETTINGS", result.settings_ok),
        ("CREDENTIALS FILE", result.credentials_file_ok),
        ("GOOGLE SERVICE", result.google_service_ok),
        ("SPREADSHEET ACCESS", result.spreadsheet_access_ok),
        ("PROGRAMMI_FORNITURA SHEET", result.programmi_sheet_ok),
        ("ORDINI SHEET", result.ordini_sheet_ok),
        ("PROGRAMMI SCHEMA", result.programmi_schema_ok),
        ("ORDINI SCHEMA", result.ordini_schema_ok),
        ("PROGRAMMI PARSING", result.programmi_parse_ok),
        ("ORDINI PARSING", result.ordini_parse_ok),
        ("SCHEDULING SIMULATION", result.scheduling_simulation_ok),
    )
    lines = ["PREFLIGHT TOWER POWER OS", ""]
    lines.extend(f"{name}: {'OK' if ok else 'FAILED'}" for name, ok in checks)
    lines.extend(
        [
            "",
            f"PROGRAMMI LETTI: {result.programmi_letti}",
            f"ORDINI ESISTENTI: {result.ordini_esistenti}",
            f"ANTEPRIME GENERATE: {result.anteprime_generate}",
        ]
    )
    if result.warnings:
        lines.extend(["", "WARNINGS:"])
        lines.extend(f"- {warning}" for warning in result.warnings)
    lines.extend(["", "ESITO PREFLIGHT: SUCCESS"])
    return "\n".join(lines)
