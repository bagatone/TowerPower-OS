"""Thin CLI adapter for Uscita Recording V1 and Uscita Correzione V1."""
from argparse import Namespace
from datetime import date
from decimal import Decimal
from typing import TextIO

from ..application.uscita.errors import (
    InvalidUscitaCommandError, UscitaError, UscitaReconciliationRequiredError,
)
from ..application.uscita.models import CorreggiUscita, RegistraUscita, UscitaAuthority
from ..bootstrap import build_uscita_service
from ..domain.errors import InvalidIdentifierError
from ..domain.identifiers import ActorId, UscitaId
from ..domain.states import CategoriaUscita, MetodoPagamento
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_uscita_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.uscita_command == "correggi":
        return _run_uscita_correggi(args, stdout=stdout, stderr=stderr)
    if args.uscita_command != "registra":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        command = RegistraUscita(
            Decimal(args.importo),
            date.fromisoformat(args.data),
            CategoriaUscita(args.categoria),
            args.beneficiario,
            MetodoPagamento(args.metodo),
            UscitaAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
            args.note,
        )
        result = build_uscita_service(
            PostgreSQLSettings.from_environment()
        ).record(command)
    except UscitaReconciliationRequiredError as exc:
        print(f"USCITA_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, InvalidIdentifierError, UscitaError) as exc:
        code = getattr(exc, "code", "USCITA_INPUT_INVALID")
        print(f"USCITA_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidIdentifierError,
                                     InvalidUscitaCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"USCITA_ID={result.uscita_id.value}", file=stdout)
    print(f"IMPORTO={result.importo}", file=stdout)
    print(f"DATA_USCITA={result.data_uscita.isoformat()}", file=stdout)
    print(f"CATEGORIA={result.categoria.value}", file=stdout)
    print(f"BENEFICIARIO={result.beneficiario}", file=stdout)
    print(f"METODO={result.metodo.value}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED


def _run_uscita_correggi(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        command = CorreggiUscita(
            UscitaId(args.originale),
            Decimal(args.importo),
            date.fromisoformat(args.data),
            CategoriaUscita(args.categoria),
            args.beneficiario,
            MetodoPagamento(args.metodo),
            UscitaAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
            args.note,
        )
        result = build_uscita_service(
            PostgreSQLSettings.from_environment()
        ).correct(command)
    except UscitaReconciliationRequiredError as exc:
        print(f"USCITA_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, InvalidIdentifierError, UscitaError) as exc:
        code = getattr(exc, "code", "USCITA_INPUT_INVALID")
        print(f"USCITA_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidIdentifierError,
                                     InvalidUscitaCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"USCITA_ID={result.uscita_id.value}", file=stdout)
    print(f"ORIGINAL_USCITA_ID={result.original_uscita_id.value}", file=stdout)
    print(f"IMPORTO={result.importo}", file=stdout)
    print(f"DATA_USCITA={result.data_uscita.isoformat()}", file=stdout)
    print(f"CATEGORIA={result.categoria.value}", file=stdout)
    print(f"BENEFICIARIO={result.beneficiario}", file=stdout)
    print(f"METODO={result.metodo.value}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
