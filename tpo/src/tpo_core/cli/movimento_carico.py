"""Thin CLI adapter for Movimento Carico Raccolta V1 (RegistraCaricoMagazzino)."""
from argparse import Namespace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TextIO

from ..application.movimento_carico.errors import (
    InvalidMovimentoCaricoCommandError,
    MovimentoCaricoError,
    MovimentoCaricoReconciliationRequiredError,
)
from ..application.movimento_carico.models import (
    MovimentoCaricoAuthority, RegistraCaricoMagazzino,
)
from ..bootstrap import build_movimento_carico_service
from ..domain.identifiers import ActorId, RaccoltaId
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_movimento_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.movimento_command != "carica-raccolta":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        try:
            quantita_pesata = Decimal(args.quantita_pesata)
        except InvalidOperation as exc:
            raise InvalidMovimentoCaricoCommandError(
                "--quantita-pesata deve essere un numero decimale."
            ) from exc
        try:
            effective_at = datetime.fromisoformat(args.effective_at)
        except ValueError as exc:
            raise InvalidMovimentoCaricoCommandError(
                "--effective-at deve essere una data/ora ISO 8601."
            ) from exc
        command = RegistraCaricoMagazzino(
            raccolta_id=RaccoltaId(args.raccolta),
            quantita_pesata=quantita_pesata,
            effective_at=effective_at,
            motivo=args.motivo,
            authority=MovimentoCaricoAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
        )
        service = build_movimento_carico_service(PostgreSQLSettings.from_environment())
        result = service.registra(command)
    except MovimentoCaricoReconciliationRequiredError as exc:
        print(f"MOVIMENTO_CARICO_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, MovimentoCaricoError) as exc:
        code = getattr(exc, "code", "MOVIMENTO_CARICO_INPUT_INVALID")
        print(f"MOVIMENTO_CARICO_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidMovimentoCaricoCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print(f"MOVIMENTO_ID={result.movimento_id.value}", file=stdout)
    print(f"RACCOLTA_ID={result.raccolta_id.value}", file=stdout)
    print(f"VARIETA_ID={result.varieta_id.value}", file=stdout)
    print(f"QUANTITA={result.quantita}", file=stdout)
    print("UOM=GRAM", file=stdout)
    print(f"EFFECTIVE_AT={result.effective_at.isoformat()}", file=stdout)
    print(f"RECORDED_AT={result.recorded_at.isoformat()}", file=stdout)
    print(f"STOCK_DISPONIBILE={result.stock_disponibile}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
