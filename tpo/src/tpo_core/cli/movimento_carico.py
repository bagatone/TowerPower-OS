"""Thin CLI adapter for Movimento Carico Raccolta (RegistraCaricoMagazzino).

V1 (GRAM, Owner Decision D11/D12): --unita-misura GRAM (default, backward
compatible), quantita' sempre dichiarata dall'operatore via --quantita-pesata.

V2 (SET, Owner Decision D13/D14): --unita-misura SET, --quantita-pesata NON
ammesso: la quantita' e' presa direttamente dalla RACCOLTA collegata (gia'
denominata SET), mai dichiarata di nuovo.
"""
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
from ..domain.quantities import UnitOfMeasure
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_movimento_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.movimento_command != "carica-raccolta":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        try:
            unita_misura = UnitOfMeasure(getattr(args, "unita_misura", "GRAM") or "GRAM")
        except ValueError as exc:
            raise InvalidMovimentoCaricoCommandError(
                "--unita-misura deve essere GRAM o SET."
            ) from exc

        quantita_pesata_raw = getattr(args, "quantita_pesata", None)
        if unita_misura is UnitOfMeasure.GRAM:
            if not quantita_pesata_raw:
                raise InvalidMovimentoCaricoCommandError(
                    "--quantita-pesata e' obbligatoria per un CARICO in GRAM."
                )
            try:
                quantita_pesata = Decimal(quantita_pesata_raw)
            except InvalidOperation as exc:
                raise InvalidMovimentoCaricoCommandError(
                    "--quantita-pesata deve essere un numero decimale."
                ) from exc
        else:
            if quantita_pesata_raw:
                raise InvalidMovimentoCaricoCommandError(
                    "--quantita-pesata non e' ammessa per un CARICO in SET: la "
                    "quantita' e' sempre presa dalla RACCOLTA collegata (D14)."
                )
            quantita_pesata = None

        try:
            effective_at = datetime.fromisoformat(args.effective_at)
        except ValueError as exc:
            raise InvalidMovimentoCaricoCommandError(
                "--effective-at deve essere una data/ora ISO 8601."
            ) from exc
        command = RegistraCaricoMagazzino(
            raccolta_id=RaccoltaId(args.raccolta),
            unita_misura=unita_misura,
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
    print(f"UOM={result.unita_misura.value}", file=stdout)
    print(f"EFFECTIVE_AT={result.effective_at.isoformat()}", file=stdout)
    print(f"RECORDED_AT={result.recorded_at.isoformat()}", file=stdout)
    print(f"STOCK_DISPONIBILE={result.stock_disponibile}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
