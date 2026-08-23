"""Composition contract for the official Production Planning runtime."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from src.tpo_core.application.production_planning.assembler import (
    ProductionPlanningCommitAssembler,
)
from src.tpo_core.application.production_planning.engine import ProductionPlanningEngine
from src.tpo_core.application.production_planning.errors import ProductionPlanningError
from src.tpo_core.application.production_planning.models import (
    PublicId, ReplanProductionPlanningCommand,
)
from src.tpo_core.application.production_planning.service import ProductionPlanningService
from src.tpo_core.bootstrap.production_planning import (
    _ProductionPlanningClockAdapter,
    build_production_planning_runtime,
    build_production_planning_runtime_from_environment,
)
from src.tpo_core.domain.time_reference import CurrentSystemDate
from src.tpo_core.infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from src.tpo_core.infrastructure.postgresql.errors import InvalidPostgreSQLSettingsError
from src.tpo_core.infrastructure.postgresql.production_planning_commit_writer import (
    PostgreSQLProductionPlanningCommitWriter,
)
from src.tpo_core.infrastructure.postgresql.production_planning_identity import (
    PostgreSQLProductionPlanningIdentityAdapter,
)
from src.tpo_core.infrastructure.postgresql.production_planning_input import (
    PostgreSQLProductionPlanningInputAdapter,
)
from src.tpo_core.infrastructure.postgresql.production_planning_run import (
    PostgreSQLProductionPlanningRunAdapter,
)
from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.integration.postgresql.test_production_planning_end_to_end import (
    _command, _seed_identity, migration_postgresql, planning_database,
    writer_cluster,
)


ENVIRONMENT = {
    "TPO_DATABASE_HOST": "db.example.invalid",
    "TPO_DATABASE_PORT": "5432",
    "TPO_DATABASE_NAME": "towerpower",
    "TPO_DATABASE_USER": "planning",
    "TPO_DATABASE_PASSWORD": "secret",
    "TPO_DATABASE_SSLMODE": "require",
    "TPO_DATABASE_CONNECT_TIMEOUT": "3",
}


class NoCallClock:
    def now(self):
        raise AssertionError("Il composition root non deve leggere il clock.")


def _settings() -> PostgreSQLSettings:
    return PostgreSQLSettings.from_environment(ENVIRONMENT)


def test_runtime_composes_the_complete_real_graph_without_io(monkeypatch):
    connect_calls = []
    monkeypatch.setattr(
        PostgreSQLConnectionFactory, "connect",
        lambda factory: connect_calls.append(factory),
    )
    clock = NoCallClock()
    runtime = build_production_planning_runtime(_settings(), clock=clock)

    assert isinstance(runtime, ProductionPlanningService)
    assert isinstance(runtime._inputs, PostgreSQLProductionPlanningInputAdapter)
    assert isinstance(runtime._runs, PostgreSQLProductionPlanningRunAdapter)
    assert isinstance(runtime._identity, PostgreSQLProductionPlanningIdentityAdapter)
    assert isinstance(runtime._engine, ProductionPlanningEngine)
    assert isinstance(runtime._assembler, ProductionPlanningCommitAssembler)
    assert isinstance(runtime._commit, PostgreSQLProductionPlanningCommitWriter)
    assert isinstance(runtime._clock, _ProductionPlanningClockAdapter)
    assert runtime._clock._clock is clock
    assert connect_calls == []

    factories = {
        runtime._inputs._connection_factory,
        runtime._runs._connection_factory,
        runtime._commit._connection_factory,
        runtime._identity._allocator._repository._connection_factory,
    }
    assert len(factories) == 1
    assert isinstance(factories.pop(), PostgreSQLConnectionFactory)


def test_environment_builder_is_deterministic_and_uses_official_configuration():
    first = build_production_planning_runtime_from_environment(
        ENVIRONMENT, clock=NoCallClock(),
    )
    second = build_production_planning_runtime_from_environment(
        ENVIRONMENT, clock=NoCallClock(),
    )
    assert type(first) is type(second) is ProductionPlanningService
    assert first is not second
    assert first._inputs._connection_factory.database_name == "towerpower"


@pytest.mark.parametrize("environment", [{}, {**ENVIRONMENT, "TPO_DATABASE_PORT": "bad"}])
def test_missing_or_invalid_database_configuration_fails_closed(environment):
    with pytest.raises(InvalidPostgreSQLSettingsError):
        build_production_planning_runtime_from_environment(environment)


def test_clock_adapter_projects_official_time_without_direct_system_calls():
    expected = CurrentSystemDate(datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc))

    class FixedClock:
        def now(self): return expected

    assert _ProductionPlanningClockAdapter(FixedClock()).now() == expected.datetime


def test_runtime_has_no_google_sheets_legacy_or_service_locator_dependency():
    module_source = inspect.getsource(
        __import__(
            "src.tpo_core.bootstrap.production_planning", fromlist=["unused"],
        )
    ).lower()
    for forbidden in ("google", "sheets", "service locator", "global "):
        assert forbidden not in module_source
    assert "datetime.now" not in module_source
    assert "datetime.utcnow" not in module_source


def test_public_runtime_api_reuses_application_execute_and_error_boundary():
    runtime = build_production_planning_runtime(_settings(), clock=NoCallClock())
    assert runtime.execute.__func__ is ProductionPlanningService.execute


def test_initial_and_replan_commands_cross_the_unchanged_error_boundary():
    initial = _command("runtime-initial")
    replan = ReplanProductionPlanningCommand(
        initial.business_at, initial.policy, initial.context,
        PublicId("RVP-000001"), PublicId("RO-000001"),
        "MANUAL_REPLAN_AUTHORIZED",
    )
    expected = ProductionPlanningError(
        "CONCURRENCY_CONFLICT", "IDENTITY_CONFLICT", "Identity in conflitto.",
    )

    class RaisingIdentity:
        def allocate(self, sequence_name): raise expected

    for command in (initial, replan):
        runtime = build_production_planning_runtime(
            _settings(), clock=NoCallClock(),
        )
        runtime._identity = RaisingIdentity()
        with pytest.raises(ProductionPlanningError) as captured:
            runtime.execute(command)
        assert captured.value is expected


def test_runtime_composition_smoke_commits_on_real_postgresql(
    planning_database, monkeypatch,
):
    _seed_identity(planning_database)
    with planning_database.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE tpo.stock SET disponibile=0 WHERE varieta_id="
            "(SELECT id FROM tpo.varieta WHERE public_id='VAR-000001')"
        )
    real_test_factory = _Factory(planning_database)
    monkeypatch.setattr(
        PostgreSQLConnectionFactory, "connect",
        lambda factory: real_test_factory.connect(),
    )

    class FixedClock:
        def now(self):
            return CurrentSystemDate(
                datetime(2026, 8, 16, 7, 0, tzinfo=timezone.utc)
            )

    result = build_production_planning_runtime(
        _settings(), clock=FixedClock(),
    ).execute(_command("runtime-smoke"))

    assert result.run_state == "COMMITTED"
