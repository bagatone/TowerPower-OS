"""Thin CLI adapter for Fattura Emissione V1.

Scope V1 (docs/architecture/FATTURA_AUTHORITY_FREEZE.md): emissione ordinaria
di una FATTURA a partire da una o più CONSEGNE evase dello stesso CLIENTE.
Nessuna rettifica/RectifyFattura: resta esplicitamente fuori scope.
"""

from __future__ import annotations

from argparse import Namespace
from datetime import date
from typing import TextIO

from ..application.fattura_emissione.errors import (
    FatturaEmissioneError,
    FatturaReconciliationRequiredError,
    InvalidEmitFatturaCommandError,
)
from ..application.fattura_emissione.models import EmitFattura, EmitFatturaAuthority
from ..bootstrap import build_fattura_emissione_service
from ..domain.identifiers import ActorId, ClienteId, ConsegnaId
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_fattura_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.fattura_command != "emetti":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        command = EmitFattura(
            cliente_id=ClienteId(args.client),
            consegna_ids=tuple(ConsegnaId(item) for item in args.consegna),
            data_emissione=_date(args.data_emissione),
            authority=EmitFatturaAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
        )
        service = build_fattura_emissione_service(PostgreSQLSettings.from_environment())
        result = service.emit(command)
    except FatturaReconciliationRequiredError as exc:
        print(f"FATTURA_EMISSIONE_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, FatturaEmissioneError) as exc:
        code = getattr(exc, "code", "FATTURA_EMISSIONE_INPUT_INVALID")
        print(f"FATTURA_EMISSIONE_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidEmitFatturaCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print(f"STATUS: {result.outcome}", file=stdout)
    print("ENTITY: FATTURA", file=stdout)
    print(f"NUMERO_FATTURA: {result.numero_fattura}", file=stdout)
    print(f"CLIENTE: {result.cliente_id.value}", file=stdout)
    print(f"DATA_EMISSIONE: {result.data_emissione.isoformat()}", file=stdout)
    print(f"SCADENZA: {result.scadenza.isoformat()}", file=stdout)
    print(f"TOTALE_NETTO: {result.totale_netto}", file=stdout)
    print(f"TOTALE_IGIC: {result.totale_igic}", file=stdout)
    print(f"TOTALE: {result.totale}", file=stdout)
    print(f"CONSEGNE: {result.consegna_count}", file=stdout)
    print(f"RIGHE: {result.riga_count}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InvalidEmitFatturaCommandError("--data-emissione deve essere una data ISO 8601.") from exc
