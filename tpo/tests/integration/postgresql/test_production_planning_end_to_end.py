"""Real PostgreSQL end-to-end contract for Production Planning."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg
import pytest

from src.tpo_core.application.identity.production_planning import (
    PRODUCTION_PLANNING_SEQUENCE_TYPES,
)
from src.tpo_core.application.identity.service import PersistentIdAllocator
from src.tpo_core.application.production_planning.assembler import (
    ProductionPlanningCommitAssembler,
)
from src.tpo_core.application.production_planning.engine import (
    ProductionPlanningEngine,
)
from src.tpo_core.application.production_planning.errors import ProductionPlanningError
from src.tpo_core.application.production_planning.models import (
    InitialProductionPlanningCommand, PlanningExecutionContext,
    PolicyVersionReference, ProductionPlanningReconciliationRequiredResult,
)
from src.tpo_core.application.production_planning.service import ProductionPlanningService
from src.tpo_core.domain.identifiers import ActorId
from src.tpo_core.infrastructure.postgresql.identity_repository import (
    PostgreSQLPersistentIdRepository,
)
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
from tests.infrastructure.postgresql.test_production_planning_commit_writer import (
    _Factory, migration_postgresql, writer_cluster,
    writer_database as planning_database,
)


TZ = ZoneInfo("Atlantic/Canary")
BUSINESS_AT = datetime(2026, 8, 15, 6, 0, tzinfo=TZ)
PERSISTENCE_AT = datetime(2026, 8, 16, 7, 0, tzinfo=TZ)


class _Clock:
    def now(self) -> datetime:
        return PERSISTENCE_AT


def _seed_identity(engine) -> None:
    with engine.begin() as connection:
        for sequence_name, identifier_type in PRODUCTION_PLANNING_SEQUENCE_TYPES.items():
            next_value = 2 if sequence_name == "RUN_PIANIFICAZIONE_PRODUZIONE_ID" else 1
            connection.exec_driver_sql(
                """INSERT INTO tpo.id_sequences
                     (sequence_name,identifier_type,prefix,next_value,version,updated_at,updated_by)
                   VALUES (%s,%s,%s,%s,0,CURRENT_TIMESTAMP,'e2e-test')""",
                (sequence_name, identifier_type.__name__, identifier_type.prefix, next_value),
            )


def _command(correlation_id: str) -> InitialProductionPlanningCommand:
    return InitialProductionPlanningCommand(
        business_at=BUSINESS_AT,
        policy=PolicyVersionReference("DEFAULT", 1),
        context=PlanningExecutionContext(
            ActorId("tpo.planning-e2e"), "Production Planning E2E", correlation_id,
        ),
    )


def _service(engine, *, commit_factory=None) -> ProductionPlanningService:
    factory = _Factory(engine)
    identity = PostgreSQLProductionPlanningIdentityAdapter(PersistentIdAllocator(
        PostgreSQLPersistentIdRepository(factory, updated_by="production-planning-e2e")
    ))
    return ProductionPlanningService(
        identity=identity,
        inputs=PostgreSQLProductionPlanningInputAdapter(factory),
        runs=PostgreSQLProductionPlanningRunAdapter(factory),
        commit=PostgreSQLProductionPlanningCommitWriter(commit_factory or factory),
        clock=_Clock(), engine=ProductionPlanningEngine(),
        assembler=ProductionPlanningCommitAssembler(),
    )


def _scalar(engine, statement: str):
    with engine.connect() as connection:
        return connection.exec_driver_sql(statement).scalar_one()


def test_happy_path_positive_production_through_all_real_adapters(planning_database):
    _seed_identity(planning_database)
    with planning_database.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE tpo.stock SET disponibile=0 WHERE varieta_id=(SELECT id FROM tpo.varieta WHERE public_id='VAR-000001')"
        )

    result = _service(planning_database).execute(_command("e2e-positive"))

    assert result.run_state == "COMMITTED"
    assert _scalar(planning_database, "SELECT state FROM tpo.production_planning_runs WHERE public_id='RPP-000002'") == "COMMITTED"
    assert _scalar(planning_database, "SELECT count(*) FROM tpo.piani_produzione") == 1
    assert _scalar(planning_database, "SELECT count(*) FROM tpo.piano_produzione_revisioni") == 1
    assert _scalar(planning_database, "SELECT count(*) FROM tpo.righe_piano_semina") == 1
    assert _scalar(planning_database, "SELECT quantita_produttiva_autorizzata FROM tpo.righe_piano_semina") > 0
    assert _scalar(planning_database, "SELECT grammi_richiesti FROM tpo.risorse_seme_pianificate") > 0
    assert _scalar(planning_database, "SELECT count(*) FROM tpo.audit_eventi WHERE planning_run_id IS NOT NULL") > 0


def test_full_stock_coverage_commits_zero_production_without_seed_child(planning_database):
    _seed_identity(planning_database)

    result = _service(planning_database).execute(_command("e2e-full-stock"))

    assert result.run_state == "COMMITTED"
    with planning_database.connect() as connection:
        line = connection.exec_driver_sql(
            """SELECT quantita_produttiva_autorizzata,grammi_seme_richiesti
               FROM tpo.righe_piano_semina"""
        ).one()
        assert line == (Decimal("0.000000"), None)
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.risorse_seme_pianificate"
        ).scalar_one() == 0
        assert connection.exec_driver_sql(
            """SELECT count(*) FROM tpo.allocazioni a
               JOIN tpo.allocazioni_stock s ON s.allocation_id=a.id
               WHERE a.allocation_type='STOCK'"""
        ).scalar_one() == 1


def test_authoritative_precommit_failure_finalizes_run_without_partial_plan(planning_database):
    _seed_identity(planning_database)
    with planning_database.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE tpo.production_planning_policy_versions SET planning_algorithm_version='unsupported-e2e'"
        )

    with pytest.raises(ProductionPlanningError):
        _service(planning_database).execute(_command("e2e-precommit-failure"))

    with planning_database.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT state FROM tpo.production_planning_runs WHERE public_id='RPP-000002'"
        ).scalar_one() == "FAILED"
        for table in ("piani_produzione", "piano_produzione_revisioni", "righe_piano_semina"):
            assert connection.exec_driver_sql(f"SELECT count(*) FROM tpo.{table}").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1


class _RaiseOnCommitConnection:
    def __init__(self, connection) -> None:
        self._connection = connection

    def commit(self):
        raise psycopg.OperationalError("fault injected before physical commit")

    def __getattr__(self, name):
        return getattr(self._connection, name)


class _RaiseOnCommitFactory(_Factory):
    def connect(self):
        return _RaiseOnCommitConnection(super().connect())


def test_uncertain_commit_requires_reconciliation_without_synthesized_commit(planning_database):
    _seed_identity(planning_database)
    fault_factory = _RaiseOnCommitFactory(planning_database)

    result = _service(planning_database, commit_factory=fault_factory).execute(
        _command("e2e-uncertain")
    )

    assert isinstance(result, ProductionPlanningReconciliationRequiredResult)
    assert result.run_state == "RECONCILIATION_REQUIRED"
    assert _scalar(planning_database, "SELECT state FROM tpo.production_planning_runs WHERE public_id='RPP-000002'") == "RECONCILIATION_REQUIRED"
    assert _scalar(planning_database, "SELECT count(*) FROM tpo.piani_produzione") == 0
