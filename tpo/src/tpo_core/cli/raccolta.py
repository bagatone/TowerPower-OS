"""Thin CLI adapter for Raccolta Recording V1 and Raccolta Correzione V1."""
from argparse import Namespace
from datetime import datetime
from decimal import Decimal
from typing import TextIO

from ..application.raccolta.errors import (
    InvalidRaccoltaCommandError, RaccoltaError, RaccoltaReconciliationRequiredError,
)
from ..application.raccolta.models import CorreggiRaccolta, RaccoltaAuthority, RecordRaccolta
from ..bootstrap import build_raccolta_service
from ..domain.errors import InvalidQuantityError, InvalidUnitOfMeasureError
from ..domain.identifiers import ActorId, RaccoltaId, SeminaId
from ..domain.quantities import Quantity, UnitOfMeasure
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_raccolta_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.raccolta_command == "correggi":
        return _run_raccolta_correggi(args, stdout=stdout, stderr=stderr)
    if args.raccolta_command != "record":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        command = RecordRaccolta(
            SeminaId(args.semina),
            Quantity(Decimal(args.quantity), UnitOfMeasure(args.uom)),
            datetime.fromisoformat(args.effective_at),
            RaccoltaAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
            args.notes,
        )
        result = build_raccolta_service(
            PostgreSQLSettings.from_environment()
        ).record(command)
    except RaccoltaReconciliationRequiredError as exc:
        print(f"RACCOLTA_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, InvalidQuantityError, InvalidUnitOfMeasureError,
            RaccoltaError) as exc:
        code = getattr(exc, "code", "RACCOLTA_INPUT_INVALID")
        print(f"RACCOLTA_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidQuantityError,
                                    InvalidUnitOfMeasureError, InvalidRaccoltaCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"RACCOLTA_ID={result.raccolta_id.value}", file=stdout)
    print(f"SEMINA_ID={result.semina_id.value}", file=stdout)
    print(f"TRACEABILITY_CODE={result.traceability_code.value}", file=stdout)
    print(f"QUANTITY={result.quantity.value}", file=stdout)
    print(f"UOM={result.quantity.unit.value}", file=stdout)
    print(f"EFFECTIVE_AT={result.effective_at.isoformat()}", file=stdout)
    print(f"RECORDED_AT={result.recorded_at.isoformat()}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED


def _run_raccolta_correggi(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        command = CorreggiRaccolta(
            RaccoltaId(args.original_raccolta),
            SeminaId(args.semina),
            Decimal(args.quantity),
            UnitOfMeasure(args.uom),
            datetime.fromisoformat(args.effective_at),
            RaccoltaAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
            args.notes,
        )
        result = build_raccolta_service(
            PostgreSQLSettings.from_environment()
        ).correct(command)
    except RaccoltaReconciliationRequiredError as exc:
        print(f"RACCOLTA_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, InvalidQuantityError, InvalidUnitOfMeasureError,
            RaccoltaError) as exc:
        code = getattr(exc, "code", "RACCOLTA_INPUT_INVALID")
        print(f"RACCOLTA_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidQuantityError,
                                    InvalidUnitOfMeasureError, InvalidRaccoltaCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"RACCOLTA_ID={result.raccolta_id.value}", file=stdout)
    print(f"ORIGINAL_RACCOLTA_ID={result.original_raccolta_id.value}", file=stdout)
    print(f"SEMINA_ID={result.semina_id.value}", file=stdout)
    print(f"TRACEABILITY_CODE={result.traceability_code.value}", file=stdout)
    print(f"QUANTITY={result.quantity}", file=stdout)
    print(f"UOM={result.unit.value}", file=stdout)
    print(f"EFFECTIVE_AT={result.effective_at.isoformat()}", file=stdout)
    print(f"RECORDED_AT={result.recorded_at.isoformat()}", file=stdout)
    print(f"NET_QUANTITY_AFTER={result.net_quantity_after}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
