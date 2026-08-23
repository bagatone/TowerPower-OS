"""PostgreSQL policy commissioning writer contract without a live provider."""

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from src.tpo_core.application.policy_commissioning import (
    CommissionProductionPlanningPolicyCommand,
    CommissionedProductionPlanningPolicy,
    PolicyCommissioningConflictError,
)
from src.tpo_core.domain.identifiers import ActorId
from src.tpo_core.infrastructure.postgresql.production_planning_policy_commissioning import (
    PostgreSQLProductionPlanningPolicyCommissioningWriter,
)


NOW = datetime(2026, 8, 23, 5, 45, tzinfo=timezone.utc)
ORIGINAL = datetime(2026, 8, 23, 5, 40, tzinfo=timezone.utc)


def _command():
    return CommissionProductionPlanningPolicyCommand(
        "DEFAULT", 1, date(2026, 8, 23), None,
        "DELIVERY_THEN_PUBLIC_ID", "production-planning-v1", "NONE", None,
        "EARLIEST_APPROVED_WINDOW",
        ActorId("tpo.production-planning-policy-commissioner"),
        "Owner-approved commissioning for Production Planning V1", None,
    )


def _row(command=None, *, approved_at=ORIGINAL):
    command = command or _command()
    return (
        command.policy_set_code, command.version,
        command.harvest_target_strategy, command.quantitative_buffer_type,
        command.quantitative_buffer_value, command.priority_policy_code,
        command.planning_algorithm_version, command.valid_from, command.valid_to,
        command.provenance, command.evidence, approved_at,
        command.actor.value, command.actor.value,
    )


class _Cursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.calls = []
        self.closed = False

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))

    def fetchone(self):
        return next(self.rows)

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, rows):
        self.cursor_value = _Cursor(rows)
        self.commits = self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class _Factory:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self.connection


def test_insert_is_append_only_and_persists_exact_explicit_payload():
    connection = _Connection([((NOW),)])
    policy = CommissionedProductionPlanningPolicy(_command(), NOW)

    result = PostgreSQLProductionPlanningPolicyCommissioningWriter(
        _Factory(connection)
    ).commission(policy)

    sql, parameters = connection.cursor_value.calls[0]
    assert "INSERT INTO tpo.production_planning_policy_versions" in sql
    assert "ON CONFLICT (policy_set_code,numero_versione) DO NOTHING" in sql
    assert "UPDATE" not in sql.upper() and "LATEST" not in sql.upper()
    assert parameters == (
        "DEFAULT", 1, "EARLIEST_APPROVED_WINDOW", "NONE", None,
        "DELIVERY_THEN_PUBLIC_ID", "production-planning-v1",
        date(2026, 8, 23), None,
        "Owner-approved commissioning for Production Planning V1", None, NOW,
        "tpo.production-planning-policy-commissioner",
        "tpo.production-planning-policy-commissioner",
    )
    assert result == policy
    assert connection.commits == 1 and connection.rollbacks == 0


def test_compatible_replay_returns_original_approved_at_without_update():
    connection = _Connection([None, _row()])
    result = PostgreSQLProductionPlanningPolicyCommissioningWriter(
        _Factory(connection)
    ).commission(CommissionedProductionPlanningPolicy(_command(), NOW))

    assert result.approved_at == ORIGINAL
    assert len(connection.cursor_value.calls) == 2
    assert all("UPDATE" not in sql.upper() for sql, _ in connection.cursor_value.calls)
    assert connection.commits == 1


def test_incompatible_duplicate_fails_closed_and_rolls_back():
    incompatible = replace(_command(), provenance="Different owner decision")
    connection = _Connection([None, _row(incompatible)])
    writer = PostgreSQLProductionPlanningPolicyCommissioningWriter(
        _Factory(connection)
    )

    with pytest.raises(PolicyCommissioningConflictError):
        writer.commission(CommissionedProductionPlanningPolicy(_command(), NOW))

    assert connection.commits == 0 and connection.rollbacks == 1
