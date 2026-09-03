"""Thin CLI adapter for Semente Impiego Commissioning V1."""

from __future__ import annotations

from argparse import Namespace
from decimal import Decimal
from typing import TextIO

from ..application.semente_impiego_commissioning.errors import (
    InvalidSementeImpiegoCommandError, SementeImpiegoCommissioningError,
    SementeImpiegoReconciliationRequiredError,
)
from ..application.semente_impiego_commissioning.models import (
    CommissionSementeImpiego, SementeImpiegoCommissioningAuthority,
)
from ..bootstrap import build_semente_impiego_commissioning_service
from ..domain.identifiers import ActorId, ProtocolloVersioneId
from ..domain.states import SementeRaccomandazione
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_semente_impiego_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        command = CommissionSementeImpiego(
            args.fornitore, args.referenza_commerciale,
            ProtocolloVersioneId(args.protocol_version),
            SementeRaccomandazione(args.raccomandazione),
            Decimal(args.rating) if args.rating is not None else None,
            args.motivazione,
            SementeImpiegoCommissioningAuthority(
                ActorId(args.actor), args.reason, args.correlation_id,
                args.idempotency_key,
            ),
        )
        service = build_semente_impiego_commissioning_service(
            PostgreSQLSettings.from_environment()
        )
        result = service.commission(command)
    except SementeImpiegoReconciliationRequiredError as exc:
        print(f"SEMENTE_IMPIEGO_COMMISSIONING_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, SementeImpiegoCommissioningError) as exc:
        code = getattr(exc, "code", "SEMENTE_IMPIEGO_INPUT_INVALID")
        print(f"SEMENTE_IMPIEGO_COMMISSIONING_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidSementeImpiegoCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"STATUS: {result.outcome}", file=stdout)
    print("ENTITY: SEMENTE_IMPIEGO", file=stdout)
    print(f"INTERNAL_ID: {result.semente_impiego_id}", file=stdout)
    print(f"SEED: {result.fornitore} / {result.referenza_commerciale}", file=stdout)
    print(f"USE: {result.varieta_public_id} / {result.cultivar_denominazione} / "
          f"{result.uso_produttivo_denominazione}", file=stdout)
    print(f"RACCOMANDAZIONE: {result.raccomandazione.value}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
