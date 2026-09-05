"""Thin CLI adapter for Assegnazione Fisica V1 (RegistraAssegnazioneFisica)."""
from argparse import Namespace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TextIO

from ..application.assegnazione_fisica.errors import (
    AssegnazioneFisicaError,
    AssegnazioneFisicaReconciliationRequiredError,
    InvalidAssegnazioneFisicaCommandError,
)
from ..application.assegnazione_fisica.models import (
    AssegnazioneFisicaAuthority, RegistraAssegnazioneFisica,
)
from ..bootstrap import build_assegnazione_fisica_service
from ..domain.identifiers import ActorId, ConsegnaId, RaccoltaId, RigaOrdineId
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_assegnazione_fisica_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.assegnazione_command != "registra":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        try:
            quantita_assegnata = Decimal(args.quantita)
        except InvalidOperation as exc:
            raise InvalidAssegnazioneFisicaCommandError(
                "--quantita deve essere un numero decimale."
            ) from exc
        try:
            effective_at = datetime.fromisoformat(args.effective_at)
        except ValueError as exc:
            raise InvalidAssegnazioneFisicaCommandError(
                "--effective-at deve essere una data/ora ISO 8601."
            ) from exc
        command = RegistraAssegnazioneFisica(
            raccolta_id=RaccoltaId(args.raccolta),
            riga_ordine_id=RigaOrdineId(args.riga_ordine),
            quantita_assegnata=quantita_assegnata,
            unita_misura=args.unita_misura,
            effective_at=effective_at,
            motivo=args.motivo,
            authority=AssegnazioneFisicaAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
            consegna_id=ConsegnaId(args.consegna) if args.consegna else None,
        )
        service = build_assegnazione_fisica_service(PostgreSQLSettings.from_environment())
        result = service.registra(command)
    except AssegnazioneFisicaReconciliationRequiredError as exc:
        print(f"ASSEGNAZIONE_FISICA_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, AssegnazioneFisicaError) as exc:
        code = getattr(exc, "code", "ASSEGNAZIONE_FISICA_INPUT_INVALID")
        print(f"ASSEGNAZIONE_FISICA_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidAssegnazioneFisicaCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print(f"ASSEGNAZIONE_FISICA_ID={result.assegnazione_fisica_id.value}", file=stdout)
    print(f"RACCOLTA_ID={result.raccolta_id.value}", file=stdout)
    print(f"RIGA_ORDINE_ID={result.riga_ordine_id.value}", file=stdout)
    print(
        f"CONSEGNA_ID={result.consegna_id.value if result.consegna_id is not None else ''}",
        file=stdout,
    )
    print(f"QUANTITA_ASSEGNATA={result.quantita_assegnata}", file=stdout)
    print(f"UOM={result.unita_misura}", file=stdout)
    print(f"EFFECTIVE_AT={result.effective_at.isoformat()}", file=stdout)
    print(f"RECORDED_AT={result.recorded_at.isoformat()}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
