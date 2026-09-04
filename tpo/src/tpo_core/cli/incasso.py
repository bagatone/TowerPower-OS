"""Thin CLI adapter for Incasso Recording V1 and Incasso Correzione V1."""
from argparse import Namespace
from datetime import date
from decimal import Decimal
from typing import TextIO

from ..application.incasso.errors import (
    IncassoError, IncassoReconciliationRequiredError, InvalidIncassoCommandError,
)
from ..application.incasso.models import CorreggiIncasso, IncassoAuthority, RegistraIncasso
from ..bootstrap import build_incasso_service
from ..domain.errors import InvalidIdentifierError
from ..domain.identifiers import ActorId, IncassoId, NumeroFattura
from ..domain.states import MetodoPagamento
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_incasso_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.incasso_command == "correggi":
        return _run_incasso_correggi(args, stdout=stdout, stderr=stderr)
    if args.incasso_command != "registra":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        command = RegistraIncasso(
            NumeroFattura(args.fattura),
            Decimal(args.importo),
            date.fromisoformat(args.data),
            MetodoPagamento(args.metodo),
            IncassoAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
            args.note,
        )
        result = build_incasso_service(
            PostgreSQLSettings.from_environment()
        ).record(command)
    except IncassoReconciliationRequiredError as exc:
        print(f"INCASSO_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, InvalidIdentifierError, IncassoError) as exc:
        code = getattr(exc, "code", "INCASSO_INPUT_INVALID")
        print(f"INCASSO_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidIdentifierError,
                                     InvalidIncassoCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"INCASSO_ID={result.incasso_id.value}", file=stdout)
    print(f"FATTURA_NUMERO={result.fattura_numero.value}", file=stdout)
    print(f"IMPORTO={result.importo}", file=stdout)
    print(f"DATA_INCASSO={result.data_incasso.isoformat()}", file=stdout)
    print(f"METODO={result.metodo.value}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED


def _run_incasso_correggi(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        command = CorreggiIncasso(
            IncassoId(args.originale),
            NumeroFattura(args.fattura),
            Decimal(args.importo),
            date.fromisoformat(args.data),
            MetodoPagamento(args.metodo),
            IncassoAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
            args.note,
        )
        result = build_incasso_service(
            PostgreSQLSettings.from_environment()
        ).correct(command)
    except IncassoReconciliationRequiredError as exc:
        print(f"INCASSO_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, InvalidIdentifierError, IncassoError) as exc:
        code = getattr(exc, "code", "INCASSO_INPUT_INVALID")
        print(f"INCASSO_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidIdentifierError,
                                     InvalidIncassoCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"INCASSO_ID={result.incasso_id.value}", file=stdout)
    print(f"ORIGINAL_INCASSO_ID={result.original_incasso_id.value}", file=stdout)
    print(f"FATTURA_NUMERO={result.fattura_numero.value}", file=stdout)
    print(f"IMPORTO={result.importo}", file=stdout)
    print(f"DATA_INCASSO={result.data_incasso.isoformat()}", file=stdout)
    print(f"METODO={result.metodo.value}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
