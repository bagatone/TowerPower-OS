"""Thin CLI delivery adapter for the official Production Planning runtime."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, TextIO

from ..application.production_planning.errors import (
    ProductionPlanningError,
    ProductionPlanningOutcomeUncertain,
    ProductionPlanningRunFinalizationOutcomeUncertain,
)
from ..application.production_planning.models import (
    InitialProductionPlanningCommand,
    PlanningExecutionContext,
    PolicyVersionReference,
    ProductionPlanningReconciliationRequiredResult,
    ProductionPlanningResult,
    PublicId,
    ReplanProductionPlanningCommand,
)
from ..bootstrap import build_production_planning_runtime_from_environment
from ..domain.identifiers import ActorId
from ..infrastructure.postgresql.errors import InvalidPostgreSQLSettingsError
from .exit_codes import OperationalExitCode


@dataclass(frozen=True)
class ProductionPlanningCliDependencies:
    runtime_factory: Callable[..., Any] = (
        build_production_planning_runtime_from_environment
    )


def run_production_planning_command(
    args: Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
    dependencies: ProductionPlanningCliDependencies | None = None,
) -> int:
    dependencies = dependencies or ProductionPlanningCliDependencies()
    try:
        command = _command(args)
    except (TypeError, ValueError, ProductionPlanningError) as exc:
        print(f"OPERATION_INPUT_INVALID: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_INPUT_INVALID

    try:
        runtime = dependencies.runtime_factory()
    except (InvalidPostgreSQLSettingsError, TypeError, ValueError):
        print("OPERATION_RUNTIME_UNAVAILABLE", file=stderr)
        return OperationalExitCode.OPERATION_RUNTIME_UNAVAILABLE

    try:
        result = runtime.execute(command)
    except ProductionPlanningRunFinalizationOutcomeUncertain as error:
        print(_format_error("RECONCILIATION_REQUIRED", error), file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except ProductionPlanningOutcomeUncertain as error:
        print(_format_error("RECONCILIATION_REQUIRED", error), file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except ProductionPlanningError as error:
        print(_format_error("PRODUCTION_PLANNING_FAILED", error), file=stderr)
        return OperationalExitCode.OPERATION_FAILED
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print(_format_result(result), file=stdout)
    if isinstance(result, ProductionPlanningReconciliationRequiredResult):
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    return OperationalExitCode.OPERATION_COMMITTED


def _command(args: Namespace):
    business_at = _business_at(args.business_at)
    policy = PolicyVersionReference(args.policy_set_code, args.policy_version)
    context = PlanningExecutionContext(
        ActorId(args.actor), args.reason, args.correlation_id,
    )
    if args.production_planning_command == "initial":
        return InitialProductionPlanningCommand(business_at, policy, context)
    if args.production_planning_command == "replan":
        return ReplanProductionPlanningCommand(
            business_at, policy, context,
            PublicId(args.previous_revision_public_id),
            PublicId(args.order_line_public_id),
            args.replanning_reason_code,
        )
    raise ValueError("Operazione Production Planning non riconosciuta.")


def _business_at(value: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("--business-at deve essere un timestamp ISO-8601.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("--business-at deve essere un timestamp ISO-8601 valido.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--business-at deve includere un offset timezone esplicito.")
    return parsed


def _format_error(prefix: str, error: ProductionPlanningError) -> str:
    return f"{prefix}: {error.category} {error.code} {error.safe_message}"


def _format_result(result) -> str:
    if isinstance(result, ProductionPlanningResult):
        lines = (
            "STATUS: COMMITTED",
            f"RUN_ID: {result.planning_run_public_id.value}",
            f"COMMITTED_AT: {result.committed_at.isoformat()}",
            f"PLAN_IDS: {_ids(result.plan_public_ids)}",
            f"CURRENT_REVISION_IDS: {_ids(result.current_revision_public_ids)}",
            f"PLANNING_LINE_IDS: {_ids(result.planning_line_public_ids)}",
            f"ALLOCATION_IDS: {_ids(result.allocation_public_ids)}",
            "WARNINGS:",
            *(f"- {item.code}: {item.message}" for item in result.warnings),
        )
        return "\n".join(lines if result.warnings else (*lines, "- nessuno"))
    if isinstance(result, ProductionPlanningReconciliationRequiredResult):
        return "\n".join((
            "STATUS: RECONCILIATION_REQUIRED",
            f"RUN_ID: {result.planning_run_public_id.value}",
            f"BUSINESS_AT: {result.business_at.isoformat()}",
            f"OBSERVED_AT: {result.observed_at.isoformat()}",
            f"CORRELATION_ID: {result.correlation_id}",
            f"FAILURE_CATEGORY: {result.failure_category}",
            f"CODE: {result.code}",
            f"MESSAGE: {result.message}",
        ))
    raise TypeError("Outcome Production Planning non riconosciuto.")


def _ids(values) -> str:
    return ",".join(item.value for item in values)
