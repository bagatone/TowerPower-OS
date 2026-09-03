"""Thin CLI adapter for Semente Commissioning V1."""

from __future__ import annotations

from argparse import Namespace
from typing import TextIO

from ..application.semente_commissioning.errors import (
    InvalidSementeCommandError, SementeCommissioningError,
    SementeReconciliationRequiredError,
)
from ..application.semente_commissioning.models import (
    CommissionSemente, SementeCommissioningAuthority,
)
from ..bootstrap import build_semente_commissioning_service
from ..domain.identifiers import ActorId
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_semente_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        command = CommissionSemente(
            args.fornitore, args.referenza_commerciale, args.marca, args.formato,
            args.trattamento, args.certificazioni,
            SementeCommissioningAuthority(
                ActorId(args.actor), args.reason, args.correlation_id,
                args.idempotency_key,
            ),
        )
        service = build_semente_commissioning_service(
            PostgreSQLSettings.from_environment()
        )
        result = service.commission(command)
    except SementeReconciliationRequiredError as exc:
        print(f"SEMENTE_COMMISSIONING_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, SementeCommissioningError) as exc:
        code = getattr(exc, "code", "SEMENTE_INPUT_INVALID")
        print(f"SEMENTE_COMMISSIONING_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidSementeCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"STATUS: {result.outcome}", file=stdout)
    print("ENTITY: SEMENTE", file=stdout)
    print(f"INTERNAL_ID: {result.semente_id}", file=stdout)
    print(f"SEED: {result.fornitore} / {result.referenza_commerciale}", file=stdout)
    print(f"ATTIVA: {result.attiva}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
