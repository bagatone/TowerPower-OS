"""Thin CLI adapter for Rettifica Giacenza (``tpo movimento rettifica-giacenza``).

Riduce la giacenza di una VARIETA quando la merce non esiste piu' fisicamente
(es. venduta senza registrazione). Non modifica nessun fatto gia' committato:
scrive un nuovo MOVIMENTO e spiega i lotti di provenienza (vedi
application/rettifica_giacenza/models.py).
"""
from argparse import Namespace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TextIO

from ..application.rettifica_giacenza.errors import (
    InvalidRettificaGiacenzaCommandError,
    RettificaGiacenzaError,
    RettificaGiacenzaReconciliationRequiredError,
)
from ..application.rettifica_giacenza.models import RettificaGiacenza, RettificaGiacenzaAuthority
from ..bootstrap import build_rettifica_giacenza_service
from ..domain.identifiers import ActorId, SeminaId, VarietaId
from ..domain.quantities import UnitOfMeasure
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_rettifica_giacenza_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        try:
            unita_misura = UnitOfMeasure(args.unita_misura)
        except ValueError as exc:
            raise InvalidRettificaGiacenzaCommandError(
                "--unita-misura deve essere GRAM o SET."
            ) from exc
        try:
            quantita = Decimal(args.quantita)
        except InvalidOperation as exc:
            raise InvalidRettificaGiacenzaCommandError(
                "--quantita deve essere un numero decimale."
            ) from exc
        try:
            effective_at = datetime.fromisoformat(args.effective_at)
        except ValueError as exc:
            raise InvalidRettificaGiacenzaCommandError(
                "--effective-at deve essere una data/ora ISO 8601."
            ) from exc
        command = RettificaGiacenza(
            varieta_id=VarietaId(args.varieta),
            unita_misura=unita_misura,
            quantita=quantita,
            effective_at=effective_at,
            motivo=args.motivo,
            authority=RettificaGiacenzaAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
            origin_semina=SeminaId(args.semina) if getattr(args, "semina", None) else None,
        )
        service = build_rettifica_giacenza_service(PostgreSQLSettings.from_environment())
        result = service.registra(command)
    except RettificaGiacenzaReconciliationRequiredError as exc:
        print(f"RETTIFICA_GIACENZA_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, RettificaGiacenzaError) as exc:
        code = getattr(exc, "code", "RETTIFICA_GIACENZA_INPUT_INVALID")
        print(f"RETTIFICA_GIACENZA_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidRettificaGiacenzaCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print(f"MOVIMENTO_ID={result.movimento_id.value}", file=stdout)
    print(f"VARIETA_ID={result.varieta_id.value}", file=stdout)
    print(f"QUANTITA={result.quantita}", file=stdout)
    print(f"UOM={result.unita_misura.value}", file=stdout)
    print(f"EFFECTIVE_AT={result.effective_at.isoformat()}", file=stdout)
    print(f"RECORDED_AT={result.recorded_at.isoformat()}", file=stdout)
    print(f"STOCK_DISPONIBILE={result.stock_disponibile}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
