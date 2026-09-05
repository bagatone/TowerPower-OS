"""Thin CLI adapter for Articolo Commissioning V1 (CommissionArticolo)."""
from argparse import Namespace
from typing import TextIO

from ..application.articolo.errors import (
    ArticoloError,
    ArticoloReconciliationRequiredError,
    InvalidArticoloCommandError,
)
from ..application.articolo.models import ArticoloCommissioningAuthority, CommissionArticolo
from ..bootstrap import build_articolo_service
from ..domain.identifiers import ActorId
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_articolo_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.articolo_command != "commissiona":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        command = CommissionArticolo(
            denominazione=args.denominazione,
            unita_misura=args.unita_misura,
            authority=ArticoloCommissioningAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
        )
        service = build_articolo_service(PostgreSQLSettings.from_environment())
        result = service.commission(command)
    except ArticoloReconciliationRequiredError as exc:
        print(f"ARTICOLO_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, ArticoloError) as exc:
        code = getattr(exc, "code", "ARTICOLO_INPUT_INVALID")
        print(f"ARTICOLO_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidArticoloCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print(f"ARTICOLO_ID={result.articolo_id.value}", file=stdout)
    print(f"DENOMINAZIONE={result.denominazione}", file=stdout)
    print(f"UOM={result.unita_misura}", file=stdout)
    print(f"RECORDED_AT={result.recorded_at.isoformat()}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
