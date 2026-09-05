"""Thin CLI adapter for Movimento Articolo V1 (RegistraMovimentoArticolo)."""
from argparse import Namespace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TextIO

from ..application.movimento_articolo.errors import (
    InvalidMovimentoArticoloCommandError,
    MovimentoArticoloError,
    MovimentoArticoloReconciliationRequiredError,
)
from ..application.movimento_articolo.models import (
    MovimentoArticoloAuthority, RegistraMovimentoArticolo,
)
from ..bootstrap import build_movimento_articolo_service
from ..domain.identifiers import ActorId, ArticoloId
from ..domain.states import MovimentoDirection, MovimentoType
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode

_TIPO_PER_COMANDO = {
    "carica-articolo": MovimentoType.CARICO,
    "scarica-articolo": MovimentoType.SCARICO,
    "rettifica-articolo": MovimentoType.RETTIFICA,
}


def run_movimento_articolo_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    tipo = _TIPO_PER_COMANDO.get(args.movimento_command)
    if tipo is None:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        try:
            quantita = Decimal(args.quantita)
        except InvalidOperation as exc:
            raise InvalidMovimentoArticoloCommandError(
                "--quantita deve essere un numero decimale."
            ) from exc
        try:
            effective_at = datetime.fromisoformat(args.effective_at)
        except ValueError as exc:
            raise InvalidMovimentoArticoloCommandError(
                "--effective-at deve essere una data/ora ISO 8601."
            ) from exc
        direzione = None
        if tipo == MovimentoType.RETTIFICA:
            if not getattr(args, "direzione", None):
                raise InvalidMovimentoArticoloCommandError(
                    "--direzione è obbligatoria per rettifica-articolo."
                )
            try:
                direzione = MovimentoDirection(args.direzione)
            except ValueError as exc:
                raise InvalidMovimentoArticoloCommandError(
                    "--direzione deve essere POSITIVO o NEGATIVO."
                ) from exc
        command = RegistraMovimentoArticolo(
            articolo_id=ArticoloId(args.articolo),
            tipo=tipo,
            quantita=quantita,
            unita_misura=args.unita_misura,
            effective_at=effective_at,
            motivo=args.motivo,
            authority=MovimentoArticoloAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
            direzione=direzione,
        )
        service = build_movimento_articolo_service(PostgreSQLSettings.from_environment())
        result = service.registra(command)
    except MovimentoArticoloReconciliationRequiredError as exc:
        print(f"MOVIMENTO_ARTICOLO_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, MovimentoArticoloError) as exc:
        code = getattr(exc, "code", "MOVIMENTO_ARTICOLO_INPUT_INVALID")
        print(f"MOVIMENTO_ARTICOLO_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidMovimentoArticoloCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print(f"MOVIMENTO_ID={result.movimento_id.value}", file=stdout)
    print(f"ARTICOLO_ID={result.articolo_id.value}", file=stdout)
    print(f"QUANTITA={result.quantita}", file=stdout)
    print(f"UOM={result.unita_misura}", file=stdout)
    print(f"EFFECTIVE_AT={result.effective_at.isoformat()}", file=stdout)
    print(f"RECORDED_AT={result.recorded_at.isoformat()}", file=stdout)
    print(f"STOCK_DISPONIBILE={result.stock_disponibile}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
