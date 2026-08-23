"""Real PostgreSQL smoke test for the Production Planning CLI boundary."""

from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timezone
from io import StringIO

from src.tpo_core.bootstrap.production_planning import build_production_planning_runtime
from src.tpo_core.cli.production_planning import (
    ProductionPlanningCliDependencies,
    run_production_planning_command,
)
from src.tpo_core.domain.time_reference import CurrentSystemDate
from src.tpo_core.infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from tests.bootstrap.test_production_planning_runtime import _settings
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.integration.postgresql.test_production_planning_end_to_end import (
    _seed_identity,
    migration_postgresql,
    planning_database,
    writer_cluster,
)


class _FixedClock:
    def now(self):
        return CurrentSystemDate(
            datetime(2026, 8, 16, 7, 0, tzinfo=timezone.utc)
        )


def test_cli_initial_reaches_real_runtime_and_commits_on_postgresql(
    planning_database, monkeypatch,
):
    _seed_identity(planning_database)
    with planning_database.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE tpo.stock SET disponibile=0 WHERE varieta_id="
            "(SELECT id FROM tpo.varieta WHERE public_id='VAR-000001')"
        )
    test_factory = _Factory(planning_database)
    monkeypatch.setattr(
        PostgreSQLConnectionFactory,
        "connect",
        lambda factory: test_factory.connect(),
    )
    cli_args = Namespace(
        production_planning_command="initial",
        business_at="2026-08-15T06:00:00+01:00",
        policy_set_code="DEFAULT",
        policy_version=1,
        actor="tpo.planning-cli-smoke",
        reason="Production Planning CLI smoke",
        correlation_id="cli-postgresql-smoke",
    )
    stdout, stderr = StringIO(), StringIO()

    code = run_production_planning_command(
        cli_args,
        stdout=stdout,
        stderr=stderr,
        dependencies=ProductionPlanningCliDependencies(
            lambda: build_production_planning_runtime(
                _settings(), clock=_FixedClock(),
            )
        ),
    )

    assert code == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue().startswith("STATUS: COMMITTED\nRUN_ID: RPP-000002\n")
    with planning_database.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT state FROM tpo.production_planning_runs "
            "WHERE public_id='RPP-000002'"
        ).scalar_one() == "COMMITTED"
