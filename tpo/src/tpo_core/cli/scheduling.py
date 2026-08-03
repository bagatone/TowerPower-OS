"""Comando CLI per una RUN dello Scheduling Engine in sola simulazione."""

from __future__ import annotations

import json
from argparse import Namespace
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, TextIO

from ..application.scheduling.models import GeneratedOrderDraft, SchedulingResult
from ..bootstrap.factory import build_application
from ..bootstrap.settings import ApplicationSettings, InvalidSettingsError, load_settings
from ..domain.errors import DomainError, InvalidTimeReferenceError
from ..domain.identifiers import InvalidIdentifierError, RunId
from ..domain.time_reference import CurrentSystemDate
from ..infrastructure.google_sheets.errors import GoogleSheetsRepositoryError
from ..infrastructure.google_sheets.google_api_gateway import build_google_sheets_service


class SimulationOnlyIdGenerator:
    """Guardia che impedisce il consumo di identificativi permanenti."""

    def next_id(self, identifier_type):
        raise RuntimeError(
            "La modalità simulazione non deve consumare identificativi permanenti."
        )


@dataclass(frozen=True)
class SchedulingCliDependencies:
    settings_loader: Callable[[str | Path], ApplicationSettings] = load_settings
    service_factory: Callable[..., Any] = build_google_sheets_service
    application_factory: Callable[..., Any] = build_application


def run_scheduling_command(
    args: Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
    dependencies: SchedulingCliDependencies | None = None,
) -> int:
    dependencies = dependencies or SchedulingCliDependencies()

    if args.simulate is not True:
        print("Argomenti non validi: --simulate è obbligatorio.", file=stderr)
        return 2

    try:
        run_id = RunId(args.run_id)
        current_system_date = _parse_current_system_date(args.current_system_date)
    except (InvalidIdentifierError, InvalidTimeReferenceError, ValueError) as exc:
        print(f"Argomenti non validi: {exc}", file=stderr)
        return 2

    try:
        settings = dependencies.settings_loader(args.settings)
    except InvalidSettingsError as exc:
        print(f"Configurazione non valida: {exc}", file=stderr)
        return 3

    try:
        service = dependencies.service_factory(
            settings.credentials_file,
            scopes=settings.scopes,
        )
    except GoogleSheetsRepositoryError as exc:
        print(f"Servizio Google Sheets non disponibile: {exc}", file=stderr)
        return 4

    try:
        container = dependencies.application_factory(
            args.settings,
            google_service=service,
            id_generator=SimulationOnlyIdGenerator(),
        )
        result = container.run_scheduling.execute(
            run_id=run_id,
            current_system_date=current_system_date,
            simulation=True,
        )
    except InvalidSettingsError as exc:
        print(f"Configurazione non valida: {exc}", file=stderr)
        return 3
    except (GoogleSheetsRepositoryError, DomainError) as exc:
        print(f"Esecuzione Scheduling non riuscita: {exc}", file=stderr)
        return 5

    if args.json_output:
        print(json.dumps(_result_payload(result), ensure_ascii=True, separators=(",", ":")), file=stdout)
    else:
        print(_format_text(result), file=stdout)
    return 0


def _parse_current_system_date(value: str) -> CurrentSystemDate:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("CURRENT_SYSTEM_DATE deve essere un datetime ISO 8601 valido.") from exc
    return CurrentSystemDate(parsed)


def _decimal_canonico(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _preview_payload(preview: GeneratedOrderDraft) -> dict[str, Any]:
    return {
        "programma_fornitura_id": preview.programma_fornitura_id.value,
        "cliente_id": preview.cliente_id.value,
        "data_ordine": preview.data_ordine.isoformat(),
        "data_consegna_prevista": preview.data_consegna_prevista.isoformat(),
        "chiave_idempotenza": preview.chiave_idempotenza,
        "righe": [
            {
                "varieta_id": riga.varieta_id.value,
                "quantita": _decimal_canonico(riga.quantita.value),
                "unita": riga.quantita.unit.value,
            }
            for riga in preview.righe
        ],
    }


def _result_payload(result: SchedulingResult) -> dict[str, Any]:
    return {
        "run_id": result.run_id.value,
        "simulation": result.simulation,
        "esito": result.esito.value,
        "programmi_letti": result.programmi_letti,
        "righe_valutate": result.righe_valutate,
        "occorrenze_valutate": result.occorrenze_valutate,
        "occorrenze_generate": result.occorrenze_generate,
        "occorrenze_saltate_per_idempotenza": result.occorrenze_saltate_per_idempotenza,
        "avvisi": list(result.avvisi),
        "anteprime": [_preview_payload(preview) for preview in result.anteprime],
    }


def _format_text(result: SchedulingResult) -> str:
    lines = [
        f"RUN_ID: {result.run_id.value}",
        "MODALITÀ: SIMULATION",
        f"ESITO: {result.esito.value}",
        f"PROGRAMMI LETTI: {result.programmi_letti}",
        f"RIGHE VALUTATE: {result.righe_valutate}",
        f"OCCORRENZE VALUTATE: {result.occorrenze_valutate}",
        f"OCCORRENZE GENERATE: {result.occorrenze_generate}",
        f"OCCORRENZE SALTATE PER IDEMPOTENZA: {result.occorrenze_saltate_per_idempotenza}",
        f"ANTEPRIME: {len(result.anteprime)}",
        "AVVISI:",
    ]
    lines.extend(f"- {warning}" for warning in result.avvisi)
    if not result.avvisi:
        lines.append("- nessuno")
    for position, preview in enumerate(result.anteprime, start=1):
        lines.extend(
            [
                f"ANTEPRIMA {position}:",
                f"  PROGRAMMA_FORNITURA_ID: {preview.programma_fornitura_id.value}",
                f"  CLIENTE_ID: {preview.cliente_id.value}",
                f"  DATA_ORDINE: {preview.data_ordine.isoformat()}",
                f"  DATA_CONSEGNA_PREVISTA: {preview.data_consegna_prevista.isoformat()}",
                f"  CHIAVE_IDEMPOTENZA: {preview.chiave_idempotenza}",
                "  RIGHE:",
            ]
        )
        lines.extend(
            f"  - {riga.varieta_id.value}: {_decimal_canonico(riga.quantita.value)} {riga.quantita.unit.value}"
            for riga in preview.righe
        )
    return "\n".join(lines)
