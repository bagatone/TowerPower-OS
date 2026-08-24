"""Real PostgreSQL commissioning and Planning Input round-trip."""

from dataclasses import replace
from argparse import Namespace
from datetime import date, datetime, timezone
from pathlib import Path
import uuid
import importlib.util
from io import StringIO

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.policy_commissioning import (
    CommissionProductionPlanningPolicyCommand,
    PolicyCommissioningConflictError,
    ProductionPlanningPolicyCommissioningService,
)
from src.tpo_core.application.production_planning.models import (
    InitialProductionPlanningCommand,
    PlanningExecutionContext,
    PolicyVersionReference,
)
from src.tpo_core.domain.identifiers import ActorId
from src.tpo_core.domain.time_reference import CurrentSystemDate
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.production_planning_input import (
    PostgreSQLProductionPlanningInputAdapter,
)
from src.tpo_core.infrastructure.postgresql.production_planning_policy_commissioning import (
    PostgreSQLProductionPlanningPolicyCommissioningWriter,
)
from src.tpo_core.bootstrap.production_planning import build_production_planning_runtime
from src.tpo_core.cli.production_planning import (
    ProductionPlanningCliDependencies,
    run_production_planning_command,
)
from src.tpo_core.infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from tests.bootstrap.test_production_planning_runtime import _settings
from tests.infrastructure.postgresql.test_production_planning_commit_writer import (
    _Factory,
    writer_cluster,
    writer_database as scheduled_planning_database,
)
from tests.integration.postgresql.test_production_planning_end_to_end import (
    _seed_identity,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql as migration_postgresql,
)


APPROVED_AT = datetime(2026, 8, 23, 5, 45, tzinfo=timezone.utc)
BUSINESS_AT = datetime(2026, 8, 23, 5, 30, tzinfo=timezone.utc)


class _Clock:
    def now(self):
        return CurrentSystemDate(APPROVED_AT)


def _command():
    return CommissionProductionPlanningPolicyCommand(
        policy_set_code="DEFAULT",
        version=1,
        valid_from=date(2026, 8, 23),
        valid_to=None,
        priority_policy_code="DELIVERY_THEN_PUBLIC_ID",
        planning_algorithm_version="production-planning-v1",
        quantitative_buffer_type="NONE",
        quantitative_buffer_value=None,
        harvest_target_strategy="EARLIEST_APPROVED_WINDOW",
        actor=ActorId("tpo.production-planning-policy-commissioner"),
        provenance="Owner-approved commissioning for Production Planning V1",
        evidence=None,
    )


@pytest.fixture
def commissioning_database(migration_postgresql):
    cluster = migration_postgresql.engine
    name = f"tpo_policy_commissioning_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    try:
        with engine.connect() as connection:
            alembic_command.upgrade(make_config(connection=connection), "head")
            connection.commit()
        yield engine
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def test_commission_default_v1_append_only_replay_and_input_roundtrip(
    commissioning_database,
):
    factory = _Factory(commissioning_database)
    service = ProductionPlanningPolicyCommissioningService(
        writer=PostgreSQLProductionPlanningPolicyCommissioningWriter(factory),
        clock=_Clock(),
    )

    first = service.commission(_command())
    replay = service.commission(_command())

    assert first == replay
    with commissioning_database.connect() as connection:
        row = connection.exec_driver_sql(
            """SELECT policy_set_code,numero_versione,valida_dal,valida_al,
                      priority_policy_code,planning_algorithm_version,
                      buffer_quantitativo_tipo,buffer_quantitativo_valore,
                      harvest_target_strategy,approved_at,approved_by,created_by,
                      provenance,evidenze
               FROM tpo.production_planning_policy_versions"""
        ).one()
    assert tuple(row) == (
        "DEFAULT", 1, date(2026, 8, 23), None,
        "DELIVERY_THEN_PUBLIC_ID", "production-planning-v1", "NONE", None,
        "EARLIEST_APPROVED_WINDOW", APPROVED_AT,
        "tpo.production-planning-policy-commissioner",
        "tpo.production-planning-policy-commissioner",
        "Owner-approved commissioning for Production Planning V1", None,
    )

    loaded = PostgreSQLProductionPlanningInputAdapter(factory).load(
        InitialProductionPlanningCommand(
            business_at=BUSINESS_AT,
            policy=PolicyVersionReference("DEFAULT", 1),
            context=PlanningExecutionContext(
                ActorId("test-reader"), "test read", "policy-roundtrip",
            ),
        )
    )
    assert loaded.snapshot.policy.reference == PolicyVersionReference("DEFAULT", 1)
    assert loaded.snapshot.policy.valid_from == date(2026, 8, 23)
    assert loaded.snapshot.policy.valid_to is None

    with pytest.raises(PolicyCommissioningConflictError):
        service.commission(replace(_command(), provenance="Different owner decision"))
    with commissioning_database.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.production_planning_policy_versions"
        ).scalar_one() == 1


def test_commissioning_import_graph_has_no_google_or_sheets_dependency():
    root = Path(__file__).resolve().parents[3]
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            root / "src/tpo_core/application/policy_commissioning"
        ).glob("*.py")
    )
    sources += (root / "src/tpo_core/infrastructure/postgresql/production_planning_policy_commissioning.py").read_text(
        encoding="utf-8"
    )
    assert "google" not in sources.lower()
    assert "sheets" not in sources.lower()


class _RuntimeClock:
    def now(self):
        return CurrentSystemDate(datetime(2026, 8, 23, 7, 0, tzinfo=timezone.utc))


def test_scheduled_cli_commissions_policy_and_replay_reuses_revision(
    scheduled_planning_database, monkeypatch,
):
    with scheduled_planning_database.begin() as connection:
        connection.exec_driver_sql("DELETE FROM tpo.production_planning_runs")
        connection.exec_driver_sql("DELETE FROM tpo.production_planning_policy_versions")
        connection.exec_driver_sql("UPDATE tpo.stock SET disponibile=0")
    factory = _Factory(scheduled_planning_database)
    ProductionPlanningPolicyCommissioningService(
        writer=PostgreSQLProductionPlanningPolicyCommissioningWriter(factory),
        clock=_Clock(),
    ).commission(_command())
    _seed_identity(scheduled_planning_database)
    monkeypatch.setattr(
        PostgreSQLConnectionFactory, "connect", lambda unused: factory.connect(),
    )
    helper_path = Path(__file__).resolve().parents[3] / "scripts/production_planning_occurrence.py"
    spec = importlib.util.spec_from_file_location("scheduled_occurrence", helper_path)
    occurrence = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(occurrence)
    business_at = occurrence.canonical_business_at(date(2026, 8, 23))
    correlation = f"production-planning-auto-v1:{business_at}"
    args = Namespace(
        production_planning_command="initial", business_at=business_at,
        policy_set_code="DEFAULT", policy_version=1,
        actor="tpo.production-planning-scheduler",
        reason="Automated Production Planning V1", correlation_id=correlation,
    )

    def invoke():
        stdout, stderr = StringIO(), StringIO()
        code = run_production_planning_command(
            args, stdout=stdout, stderr=stderr,
            dependencies=ProductionPlanningCliDependencies(
                lambda: build_production_planning_runtime(
                    _settings(), clock=_RuntimeClock(),
                )
            ),
        )
        assert code == 0, stderr.getvalue()
        assert stderr.getvalue() == ""
        return stdout.getvalue()

    assert "STATUS: COMMITTED" in invoke()
    with scheduled_planning_database.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.production_planning_runs"
        ).scalar_one() == 1
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.piano_produzione_revisioni"
        ).scalar_one() == 1

    assert "STATUS: COMMITTED" in invoke()
    with scheduled_planning_database.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.production_planning_runs"
        ).scalar_one() == 2
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.piano_produzione_revisioni"
        ).scalar_one() == 1
