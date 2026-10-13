"""Thin CLI adapter per PAGAMENTO CONSEGNA V1 (registra / annulla)."""
from argparse import Namespace
from datetime import date
from decimal import Decimal
from typing import TextIO

from ..application.pagamento_consegna.errors import (
    InvalidPagamentoConsegnaCommandError, PagamentoConsegnaError,
    PagamentoConsegnaReconciliationRequiredError,
)
from ..application.pagamento_consegna.models import (
    AnnullaPagamentoConsegna, PagamentoConsegnaAuthority, RegistraPagamentoConsegna,
)
from ..bootstrap import build_pagamento_consegna_service
from ..domain.errors import InvalidIdentifierError
from ..domain.identifiers import ActorId, ConsegnaId, PagamentoConsegnaId
from ..domain.states import MetodoPagamento
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_pagamento_consegna_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.pagamento_consegna_command not in {"registra", "annulla"}:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        authority = PagamentoConsegnaAuthority(
            ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
        )
        service = None
        if args.pagamento_consegna_command == "registra":
            command = RegistraPagamentoConsegna(
                ConsegnaId(args.consegna), date.fromisoformat(args.data),
                MetodoPagamento(args.metodo), authority,
                None if args.importo is None else Decimal(args.importo),
                args.note, bool(args.storico),
            )
            service = build_pagamento_consegna_service(PostgreSQLSettings.from_environment())
            result = service.record(command)
        else:
            command = AnnullaPagamentoConsegna(PagamentoConsegnaId(args.originale), authority,
                                               args.note)
            service = build_pagamento_consegna_service(PostgreSQLSettings.from_environment())
            result = service.cancel(command)
    except PagamentoConsegnaReconciliationRequiredError as exc:
        print(f"PAGAMENTO_CONSEGNA_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, ArithmeticError, InvalidIdentifierError,
            PagamentoConsegnaError) as exc:
        code = getattr(exc, "code", "PAGAMENTO_CONSEGNA_INPUT_INVALID")
        print(f"PAGAMENTO_CONSEGNA_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, ArithmeticError,
                                    InvalidIdentifierError,
                                    InvalidPagamentoConsegnaCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    if args.pagamento_consegna_command == "registra":
        print(f"PAGAMENTO_CONSEGNA_ID={result.pagamento_id.value}", file=stdout)
        print(f"CONSEGNA={result.consegna_id.value}", file=stdout)
        print(f"DATA_PAGAMENTO={result.data_pagamento.isoformat()}", file=stdout)
        print(f"METODO={result.metodo.value}", file=stdout)
        print(f"IMPORTO={'' if result.importo is None else result.importo}", file=stdout)
        print(f"STORICO={'SI' if result.storico else 'NO'}", file=stdout)
    else:
        print(f"PAGAMENTO_CONSEGNA_ANNULLAMENTO_ID={result.annullamento_id.value}", file=stdout)
        print(f"PAGAMENTO_CONSEGNA_ID={result.pagamento_id.value}", file=stdout)
        print(f"CONSEGNA={result.consegna_id.value}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
