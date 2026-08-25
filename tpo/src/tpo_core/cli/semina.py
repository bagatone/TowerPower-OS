"""Thin CLI adapter for Semina Commissioning V1."""
from argparse import Namespace
from datetime import datetime
from decimal import Decimal
import json
from typing import TextIO

from ..application.semina_commissioning.errors import (
    InvalidSeminaCommandError, SeminaCommissioningError, SeminaReconciliationRequiredError,
)
from ..application.semina_commissioning.models import (
    CommissionSemina, PlannedSeminaStart, SeminaCommissioningAuthority,
    SeminaFactSource, SeminaOrigin,
)
from ..application.semina_lifecycle.errors import (
    InvalidSeminaLifecycleCommandError, SeminaLifecycleError,
    SeminaLifecycleReconciliationRequiredError,
)
from ..application.semina_lifecycle.models import (
    SeminaFinalOutcome, SeminaLifecycleAuthority, TransitionSemina,
)
from ..bootstrap import build_semina_commissioning_service, build_semina_lifecycle_service
from ..domain.identifiers import (
    ActorId, LottoSemeId, ProtocolloVersioneId, RigaPianoSeminaId, SeminaId,
)
from ..domain.quantities import Quantity, UnitOfMeasure
from ..domain.states import SeminaState
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_semina_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.semina_command == "transition":
        return _run_transition(args, stdout=stdout, stderr=stderr)
    try:
        raw = json.loads(args.provenance)
        if not isinstance(raw, dict):
            raise InvalidSeminaCommandError("--provenance richiede un oggetto JSON.")
        planning = None
        supplied = (args.planning_line, args.expected_planning_line_version,
                    args.started_quantity_set)
        if any(value is not None for value in supplied):
            if not all(value is not None for value in supplied):
                raise InvalidSeminaCommandError("I tre argomenti Planning sono atomici.")
            planning = PlannedSeminaStart(
                RigaPianoSeminaId(args.planning_line), args.expected_planning_line_version,
                Quantity(Decimal(args.started_quantity_set), UnitOfMeasure.SET),
            )
        command = CommissionSemina(
            LottoSemeId(args.seed_lot), args.expected_seed_lot_version,
            ProtocolloVersioneId(args.protocol_version),
            Quantity(Decimal(args.actual_seed_grams), UnitOfMeasure.GRAM),
            datetime.fromisoformat(args.physical_started_at), SeminaOrigin(args.origin), planning,
            tuple((field, SeminaFactSource(source)) for field, source in raw.items()),
            SeminaCommissioningAuthority(ActorId(args.actor), args.reason,
                                         args.correlation_id, args.idempotency_key),
        )
        result = build_semina_commissioning_service(
            PostgreSQLSettings.from_environment()
        ).commission(command)
    except SeminaReconciliationRequiredError as exc:
        print(f"SEMINA_COMMISSIONING_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, json.JSONDecodeError, SeminaCommissioningError) as exc:
        code = getattr(exc, "code", "SEMINA_INPUT_INVALID")
        print(f"SEMINA_COMMISSIONING_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, json.JSONDecodeError,
                                    InvalidSeminaCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"STATUS: {result.outcome}", file=stdout)
    print("ENTITY: SEMINA", file=stdout)
    print(f"PUBLIC_ID: {result.semina_id.value}", file=stdout)
    print(f"STATE: {result.state}", file=stdout)
    print(f"SEED_LOT: {result.seed_lot_id.value}", file=stdout)
    print(f"SEED_LOT_VERSION: {result.seed_lot_version}", file=stdout)
    print(f"RESIDUAL_SEED: {result.remaining_seed_quantity.value} GRAM", file=stdout)
    if result.planning_line_id:
        print(f"PLANNING_LINE: {result.planning_line_id.value}", file=stdout)
        print(f"PLANNING_LINE_VERSION: {result.planning_line_version}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED


def _run_transition(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        raw = json.loads(args.provenance)
        if not isinstance(raw, dict):
            raise InvalidSeminaLifecycleCommandError("--provenance richiede un oggetto JSON.")
        command = TransitionSemina(
            SeminaId(args.semina), args.expected_semina_version,
            SeminaState(args.target_state), datetime.fromisoformat(args.effective_at),
            SeminaFinalOutcome(args.final_outcome) if args.final_outcome else None,
            tuple((field, SeminaFactSource(source)) for field, source in raw.items()),
            SeminaLifecycleAuthority(ActorId(args.actor), args.reason,
                                     args.correlation_id, args.idempotency_key),
        )
        result = build_semina_lifecycle_service(
            PostgreSQLSettings.from_environment()
        ).transition(command)
    except SeminaLifecycleReconciliationRequiredError as exc:
        print(f"SEMINA_LIFECYCLE_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, json.JSONDecodeError, SeminaLifecycleError) as exc:
        code = getattr(exc, "code", "SEMINA_LIFECYCLE_INPUT_INVALID")
        print(f"SEMINA_LIFECYCLE_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, json.JSONDecodeError,
                                    InvalidSeminaLifecycleCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"STATUS: {result.outcome}", file=stdout)
    print("ENTITY: SEMINA", file=stdout)
    print(f"PUBLIC_ID: {result.semina_public_id.value}", file=stdout)
    print(f"FROM_STATE: {result.previous_state.value}", file=stdout)
    print(f"STATE: {result.resulting_state.value}", file=stdout)
    if result.final_outcome:
        print(f"FINAL_OUTCOME: {result.final_outcome.value}", file=stdout)
    print(f"EFFECTIVE_AT: {result.effective_at.isoformat()}", file=stdout)
    print(f"RECORDED_AT: {result.recorded_at.isoformat()}", file=stdout)
    print(f"VERSION: {result.version_after}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
