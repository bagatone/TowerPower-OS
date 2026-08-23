"""Delivery contract for the Production Planning CLI."""

from __future__ import annotations

from argparse import Namespace
from datetime import datetime
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.production_planning.errors import (
    ProductionPlanningError, ProductionPlanningOutcomeUncertain,
)
from src.tpo_core.application.production_planning.models import (
    InitialProductionPlanningCommand,
    ProductionPlanningReconciliationRequiredResult,
    PublicId,
    ReplanProductionPlanningCommand,
)
from src.tpo_core.cli.exit_codes import OperationalExitCode
from src.tpo_core.cli.production_planning import (
    ProductionPlanningCliDependencies, run_production_planning_command,
)
from src.tpo_core.infrastructure.postgresql.errors import InvalidPostgreSQLSettingsError
from tests.application.production_planning.test_application_layer import result


TZ = ZoneInfo("Atlantic/Canary")


def args(operation="initial", **overrides):
    values = {
        "production_planning_command": operation,
        "business_at": "2026-08-23T12:00:00+01:00",
        "policy_set_code": "DEFAULT",
        "policy_version": 3,
        "actor": "planner-1",
        "reason": "Pianificazione esplicita",
        "correlation_id": "corr-123",
    }
    if operation == "replan":
        values.update({
            "previous_revision_public_id": "RVP-000321",
            "order_line_public_id": "RO-000654",
            "replanning_reason_code": "STOCK_CHANGED",
        })
    values.update(overrides)
    return Namespace(**values)


class Runtime:
    def __init__(self, outcome=None, error=None):
        self.outcome = outcome or result(PublicId("RPP-000001"))
        self.error = error
        self.calls = []

    def execute(self, command):
        self.calls.append(command)
        if self.error: raise self.error
        return self.outcome


def execute(cli_args=None, *, outcome=None, runtime_error=None, factory_error=None):
    runtime = Runtime(outcome, runtime_error)
    factory_calls = []

    def factory():
        factory_calls.append(True)
        if factory_error: raise factory_error
        return runtime

    stdout, stderr = StringIO(), StringIO()
    code = run_production_planning_command(
        cli_args or args(), stdout=stdout, stderr=stderr,
        dependencies=ProductionPlanningCliDependencies(factory),
    )
    return code, stdout.getvalue(), stderr.getvalue(), factory_calls, runtime


def test_initial_constructs_exact_existing_command_and_calls_runtime_once():
    code, output, error, factories, runtime = execute()
    command = runtime.calls[0]
    assert code == 0 and error == "" and factories == [True]
    assert isinstance(command, InitialProductionPlanningCommand)
    assert not isinstance(command, ReplanProductionPlanningCommand)
    assert command.business_at.isoformat() == "2026-08-23T12:00:00+01:00"
    assert command.policy.policy_set_code == "DEFAULT" and command.policy.version == 3
    assert command.context.actor.value == "planner-1"
    assert command.context.reason == "Pianificazione esplicita"
    assert command.context.correlation_id == "corr-123"
    assert output.startswith("STATUS: COMMITTED\nRUN_ID: RPP-000001\n")
    assert len(runtime.calls) == 1


def test_replan_constructs_exact_existing_command_without_inference():
    code, _, _, _, runtime = execute(args("replan"))
    command = runtime.calls[0]
    assert code == 0 and isinstance(command, ReplanProductionPlanningCommand)
    assert command.previous_revision_public_id == PublicId("RVP-000321")
    assert command.order_line_public_id == PublicId("RO-000654")
    assert command.replanning_reason_code == "STOCK_CHANGED"


@pytest.mark.parametrize("business_at", [
    "2026-08-23T12:00:00", "not-a-date", "2026-02-30T12:00:00+01:00", "",
])
def test_invalid_or_naive_business_timestamp_fails_before_runtime(business_at):
    code, output, error, factories, runtime = execute(args(business_at=business_at))
    assert code == OperationalExitCode.OPERATION_INPUT_INVALID == 2
    assert output == "" and "OPERATION_INPUT_INVALID" in error
    assert factories == [] and runtime.calls == []


def test_success_output_is_deterministic_and_provider_neutral():
    first = execute()[1]
    second = execute()[1]
    assert first == second
    assert "PLAN_IDS: PP-000001" in first
    assert "CURRENT_REVISION_IDS: RVP-000001" in first
    assert "WARNINGS:\n- nessuno" in first


def test_expected_failure_is_sanitized_and_mapped_to_exit_one():
    failure = ProductionPlanningError(
        "PLANNING_INFEASIBLE", "DEADLINE_IMPOSSIBLE", "Piano non fattibile.",
    )
    code, output, error, _, runtime = execute(runtime_error=failure)
    assert code == OperationalExitCode.OPERATION_FAILED == 1
    assert output == ""
    assert error == "PRODUCTION_PLANNING_FAILED: PLANNING_INFEASIBLE DEADLINE_IMPOSSIBLE Piano non fattibile.\n"
    assert len(runtime.calls) == 1


def test_uncertain_error_and_reconciliation_result_are_distinct_exit_four():
    code, output, error, _, _ = execute(runtime_error=ProductionPlanningOutcomeUncertain())
    assert code == 4 and output == "" and error.startswith("RECONCILIATION_REQUIRED:")
    uncertain = ProductionPlanningReconciliationRequiredResult(
        PublicId("RPP-000001"), "RECONCILIATION_REQUIRED",
        datetime(2026, 8, 23, 12, tzinfo=TZ),
        datetime(2026, 8, 23, 13, tzinfo=TZ), "corr-123",
        "RECONCILIATION_REQUIRED", "COMMIT_OUTCOME_UNCERTAIN",
        "Esito da riconciliare.",
    )
    code, output, error, _, _ = execute(outcome=uncertain)
    assert code == 4 and error == ""
    assert output.startswith("STATUS: RECONCILIATION_REQUIRED")
    assert "CORRELATION_ID: corr-123" in output


def test_configuration_failure_exposes_no_secret():
    secret = "password-do-not-print"
    failure = InvalidPostgreSQLSettingsError(f"invalid {secret}")
    code, output, error, factories, runtime = execute(factory_error=failure)
    assert code == 3 and output == "" and error == "OPERATION_RUNTIME_UNAVAILABLE\n"
    assert secret not in error and factories == [True] and runtime.calls == []


def test_cli_source_has_no_database_google_or_legacy_dependency():
    source = Path("src/tpo_core/cli/production_planning.py").read_text().lower()
    for forbidden in (
        "psycopg", "google", "sheetsloader", "eventengine",
        "productionplanningcommitwriter", "identityallocation",
    ):
        assert forbidden not in source
