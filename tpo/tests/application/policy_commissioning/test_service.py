"""Application contract for Production Planning policy commissioning."""

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from src.tpo_core.application.policy_commissioning import (
    CommissionProductionPlanningPolicyCommand,
    InvalidPolicyCommissioningCommandError,
    ProductionPlanningPolicyCommissioningService,
)
from src.tpo_core.domain.identifiers import ActorId
from src.tpo_core.domain.time_reference import CurrentSystemDate


APPROVED_AT = datetime(2026, 8, 23, 5, 45, tzinfo=timezone.utc)


def command(**overrides):
    values = {
        "policy_set_code": "DEFAULT",
        "version": 1,
        "valid_from": date(2026, 8, 23),
        "valid_to": None,
        "priority_policy_code": "DELIVERY_THEN_PUBLIC_ID",
        "planning_algorithm_version": "production-planning-v1",
        "quantitative_buffer_type": "NONE",
        "quantitative_buffer_value": None,
        "harvest_target_strategy": "EARLIEST_APPROVED_WINDOW",
        "actor": ActorId("tpo.production-planning-policy-commissioner"),
        "provenance": "Owner-approved commissioning for Production Planning V1",
        "evidence": None,
    }
    values.update(overrides)
    return CommissionProductionPlanningPolicyCommand(**values)


class _Clock:
    calls = 0

    def now(self):
        self.calls += 1
        return CurrentSystemDate(APPROVED_AT)


class _Writer:
    def __init__(self):
        self.calls = []

    def commission(self, policy):
        self.calls.append(policy)
        return policy


def test_exact_default_v1_uses_official_clock_and_writer_once():
    writer, clock = _Writer(), _Clock()
    result = ProductionPlanningPolicyCommissioningService(
        writer=writer, clock=clock,
    ).commission(command())

    assert result.command.policy_set_code == "DEFAULT"
    assert result.command.version == 1
    assert result.command.valid_from == date(2026, 8, 23)
    assert result.command.valid_to is None
    assert result.command.priority_policy_code == "DELIVERY_THEN_PUBLIC_ID"
    assert result.command.planning_algorithm_version == "production-planning-v1"
    assert result.command.quantitative_buffer_type == "NONE"
    assert result.command.quantitative_buffer_value is None
    assert result.command.harvest_target_strategy == "EARLIEST_APPROVED_WINDOW"
    assert result.command.actor == ActorId("tpo.production-planning-policy-commissioner")
    assert result.command.provenance == "Owner-approved commissioning for Production Planning V1"
    assert result.command.evidence is None
    assert result.approved_at == APPROVED_AT
    assert clock.calls == 1 and writer.calls == [result]


@pytest.mark.parametrize(
    "changes",
    (
        {"version": 0},
        {"priority_policy_code": "OTHER"},
        {"planning_algorithm_version": "production-planning-v2"},
        {"quantitative_buffer_type": "NONE", "quantitative_buffer_value": 1},
        {"harvest_target_strategy": "LATEST"},
        {"actor": "tpo.production-planning-policy-commissioner"},
        {"provenance": ""},
    ),
)
def test_v1_invariants_fail_closed_without_defaults(changes):
    with pytest.raises(InvalidPolicyCommissioningCommandError):
        command(**changes)


def test_command_is_fully_explicit_and_has_no_latest_selection():
    fields = CommissionProductionPlanningPolicyCommand.__dataclass_fields__
    assert all(field.default is field.default_factory for field in fields.values())
    assert "latest" not in " ".join(fields).lower()
    assert replace(command(), version=2).version == 2
