"""Thin CLI adapter for Seed Lot Commissioning V1."""

from __future__ import annotations

from argparse import Namespace
from datetime import date
from decimal import Decimal
import json
from typing import TextIO

from ..application.seed_lot_commissioning.errors import (
    InvalidSeedLotCommandError, SeedLotCommissioningError,
    SeedLotReconciliationRequiredError,
)
from ..application.seed_lot_commissioning.models import (
    CommissionSeedLot, SeedLotCommissioningAuthority, SeedLotFactSource,
)
from ..bootstrap import build_seed_lot_commissioning_service
from ..domain.identifiers import ActorId
from ..domain.quantities import Quantity, UnitOfMeasure
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_seed_lot_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        provenance_data = json.loads(args.provenance)
        if not isinstance(provenance_data, dict):
            raise InvalidSeedLotCommandError("--provenance richiede un oggetto JSON.")
        provenance = tuple(
            (field, SeedLotFactSource(source)) for field, source in provenance_data.items()
        )
        command = CommissionSeedLot(
            args.seed_supplier, args.seed_commercial_reference,
            args.manufacturer_lot_number, date.fromisoformat(args.received_date),
            date.fromisoformat(args.expiry_date) if args.expiry_date else None,
            Quantity(Decimal(args.initial_quantity), UnitOfMeasure(args.unit)),
            args.anomaly, provenance,
            SeedLotCommissioningAuthority(
                ActorId(args.actor), args.reason, args.correlation_id,
                args.idempotency_key,
            ),
        )
        service = build_seed_lot_commissioning_service(
            PostgreSQLSettings.from_environment()
        )
        result = service.commission(command)
    except SeedLotReconciliationRequiredError as exc:
        print(f"SEED_LOT_COMMISSIONING_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, json.JSONDecodeError, SeedLotCommissioningError) as exc:
        code = getattr(exc, "code", "SEED_LOT_INPUT_INVALID")
        print(f"SEED_LOT_COMMISSIONING_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, json.JSONDecodeError,
                                    InvalidSeedLotCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"STATUS: {result.outcome}", file=stdout)
    print("ENTITY: LOTTO_SEME", file=stdout)
    print(f"PUBLIC_ID: {result.seed_lot_id.value}", file=stdout)
    print(f"SEED: {result.seed_supplier} / {result.seed_commercial_reference}", file=stdout)
    print(f"MANUFACTURER_LOT: {result.manufacturer_lot_number}", file=stdout)
    print(f"INITIAL_QUANTITY: {result.initial_quantity.value} GRAM", file=stdout)
    print(f"RESIDUAL_QUANTITY: {result.remaining_quantity.value} GRAM", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
