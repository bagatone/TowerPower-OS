"""Unit contract for the PostgreSQL Production Planning RUN adapter."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.production_planning.errors import (
    ProductionPlanningError,
    ProductionPlanningOutcomeUncertain,
)
from src.tpo_core.application.production_planning.models import (
    PolicyVersionReference, ProductionPlanningRunSnapshot, PublicId, RunMessage,
)
from src.tpo_core.infrastructure.postgresql.production_planning_run import (
    PostgreSQLProductionPlanningRunAdapter,
)


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=ZoneInfo("Atlantic/Canary"))


class Cursor:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.current = []
        self.sql = []

    def execute(self, statement, parameters=()):
        self.sql.append((" ".join(statement.split()), parameters))
        self.current = next(self.responses)

    def fetchall(self): return self.current
    def fetchone(self): return self.current[0] if self.current else None
    def close(self): pass


class Connection:
    def __init__(self, responses):
        self.cursor_value = Cursor(responses)
        self.commits = 0
        self.rollbacks = 0
    def cursor(self): return self.cursor_value
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1
    def close(self): pass


class Factory:
    def __init__(self, connection): self.connection = connection
    def connect(self): return self.connection


def test_open_persists_exact_frozen_run_fields_once():
    connection = Connection([[(17,)], [("RPP-000001", 0, "OPEN")]])
    adapter = PostgreSQLProductionPlanningRunAdapter(Factory(connection))
    result = adapter.open(
        public_id=PublicId("RPP-000001"), policy=PolicyVersionReference("DEFAULT", 1),
        business_at=NOW, started_at=NOW, created_by="planner",
    )
    assert result == ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN")
    insert = connection.cursor_value.sql[1][0]
    assert "correlation" not in insert.lower() and "reason" not in insert.lower()
    assert connection.commits == 1


def test_finalize_failure_is_one_open_cas_and_messages_are_atomic():
    connection = Connection([[(41,)], []])
    adapter = PostgreSQLProductionPlanningRunAdapter(Factory(connection))
    error = ProductionPlanningError("PLANNING_INPUT_INVALID", "BAD_INPUT", "Input non valido.")
    adapter.finalize_failure(
        run=ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN"),
        completed_at=NOW, error=error,
        messages=(RunMessage(1, "ERROR", error.code, error.safe_message, NOW, error.category),),
    )
    update = connection.cursor_value.sql[0]
    assert "state='OPEN'" in update[0] and "version=%s" in update[0]
    assert update[1][0] == "FAILED" and connection.commits == 1


def test_reconciliation_returns_only_frozen_uncertain_result():
    connection = Connection([[(41,)], []])
    adapter = PostgreSQLProductionPlanningRunAdapter(Factory(connection))
    result = adapter.require_reconciliation(
        run=ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN"),
        business_at=NOW, observed_at=NOW, correlation_id="corr-1",
        error=ProductionPlanningOutcomeUncertain(),
    )
    assert result.run_state == "RECONCILIATION_REQUIRED"
    assert result.planning_run_public_id == PublicId("RPP-000001")
    assert connection.commits == 1


def test_invalid_run_transition_fails_closed_and_rolls_back():
    connection = Connection([[]])
    adapter = PostgreSQLProductionPlanningRunAdapter(Factory(connection))
    error = ProductionPlanningError("PLANNING_INPUT_INVALID", "BAD_INPUT", "Input non valido.")
    with pytest.raises(ProductionPlanningError, match="RUN assente"):
        adapter.finalize_failure(
            run=ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN"),
            completed_at=NOW, error=error, messages=(),
        )
    assert connection.commits == 0 and connection.rollbacks == 1
