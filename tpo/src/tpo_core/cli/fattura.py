"""Thin CLI adapter for Fattura Emissione V1 e Fattura Rettifica V1.

Scope (docs/architecture/FATTURA_AUTHORITY_FREEZE.md,
docs/architecture/RECTIFY_FATTURA_AUTHORITY_FREEZE.md): emissione ordinaria di
una FATTURA a partire da una o più CONSEGNE evase dello stesso CLIENTE
(`emetti`), e rettifica per singola riga di una FATTURA già emessa
(`rettifica`).
"""

from __future__ import annotations

from argparse import Namespace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TextIO

from ..application.fattura_emissione.errors import (
    FatturaEmissioneError,
    FatturaReconciliationRequiredError,
    InvalidEmitFatturaCommandError,
)
from ..application.fattura_emissione.models import EmitFattura, EmitFatturaAuthority
from ..application.fattura_rettifica.errors import (
    FatturaRettificaError,
    FatturaRettificaReconciliationRequiredError,
    InvalidRectifyFatturaCommandError,
)
from ..application.fattura_rettifica.models import (
    RectifyFattura, RectifyFatturaAuthority, RettificaRigaFattura,
)
from ..bootstrap import build_fattura_emissione_service, build_fattura_rettifica_service
from ..domain.identifiers import ActorId, ClienteId, ConsegnaId, NumeroFattura
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_fattura_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.fattura_command == "emetti":
        return _run_emetti(args, stdout=stdout, stderr=stderr)
    if args.fattura_command == "rettifica":
        return _run_rettifica(args, stdout=stdout, stderr=stderr)
    print("OPERATION_INTERNAL_ERROR", file=stderr)
    return OperationalExitCode.OPERATION_INTERNAL_ERROR


def _run_emetti(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
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


def _run_rettifica(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        command = RectifyFattura(
            rettifica_di=NumeroFattura(args.rettifica_di),
            righe=tuple(_riga(item) for item in args.riga),
            data_emissione=_date(args.data_emissione, error=InvalidRectifyFatturaCommandError),
            authority=RectifyFatturaAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
        )
        service = build_fattura_rettifica_service(PostgreSQLSettings.from_environment())
        result = service.rectify(command)
    except FatturaRettificaReconciliationRequiredError as exc:
        print(f"FATTURA_RETTIFICA_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, FatturaRettificaError) as exc:
        code = getattr(exc, "code", "FATTURA_RETTIFICA_INPUT_INVALID")
        print(f"FATTURA_RETTIFICA_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidRectifyFatturaCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print(f"STATUS: {result.outcome}", file=stdout)
    print("ENTITY: FATTURA", file=stdout)
    print(f"NUMERO_FATTURA: {result.numero_fattura}", file=stdout)
    print(f"RETTIFICA_DI: {result.rettifica_di}", file=stdout)
    print(f"CLIENTE: {result.cliente_id.value}", file=stdout)
    print(f"DATA_EMISSIONE: {result.data_emissione.isoformat()}", file=stdout)
    print(f"SCADENZA: {result.scadenza.isoformat()}", file=stdout)
    print(f"TOTALE_NETTO: {result.totale_netto}", file=stdout)
    print(f"TOTALE_IGIC: {result.totale_igic}", file=stdout)
    print(f"TOTALE: {result.totale}", file=stdout)
    print(f"RIGHE: {result.riga_count}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED


def _riga(value: str) -> RettificaRigaFattura:
    posizione_str, sep, quantita_str = value.partition(":")
    if not sep:
        raise InvalidRectifyFatturaCommandError(
            "--riga deve avere il formato POSIZIONE:QUANTITA (es. 1:-2.5)."
        )
    try:
        posizione = int(posizione_str)
    except ValueError as exc:
        raise InvalidRectifyFatturaCommandError("--riga: POSIZIONE deve essere un intero.") from exc
    try:
        quantita = Decimal(quantita_str)
    except InvalidOperation as exc:
        raise InvalidRectifyFatturaCommandError("--riga: QUANTITA deve essere un numero decimale.") from exc
    return RettificaRigaFattura(posizione_originale=posizione, quantita=quantita)


def _date(value: str, *, error: type[Exception] = InvalidEmitFatturaCommandError) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise error("--data-emissione deve essere una data ISO 8601.") from exc
