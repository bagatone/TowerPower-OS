"""Composizione esplicita delle dipendenze applicative."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..application.committer.service import ApplicationCommitter
from ..application.identity.service import PersistentIdAllocator
from ..application.operational_entrypoint.context import (
    OperationalExecutionContextFactory,
    UuidCorrelationIdGenerator,
)
from ..application.operational_entrypoint.service import OperationalSchedulingEntryPoint
from ..application.operational_scheduling.orchestrator import (
    OperationalSchedulingOrchestrator,
)
from ..application.operational_scheduling.use_case import ExecuteSchedulingCommit
from ..application.run_tracking.service import SchedulingRunService
from ..application.scheduling.engine import SchedulingEngine
from ..application.scheduling.use_case import RunScheduling
from ..application.write_plan.service import WritePlanBuilder
from ..application.write_plan.validation import WritePlanValidator
from ..domain.identifiers import IdGenerator
from ..application.ports.clock import Clock
from ..infrastructure.clock import SystemClock
from ..infrastructure.google_sheets.google_api_gateway import GoogleApiSheetsGateway
from ..infrastructure.google_sheets.ordini_repository import GoogleSheetsOrdineRepository
from ..infrastructure.google_sheets.programmi_repository import (
    GoogleSheetsProgrammaFornituraRepository,
)
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.commit_repository import PostgreSQLCommitRepository
from ..infrastructure.postgresql.health import PostgreSQLHealthCheck
from ..infrastructure.postgresql.identity_repository import PostgreSQLPersistentIdRepository
from ..infrastructure.postgresql.orders_repository import PostgreSQLOrdineRepository
from ..infrastructure.postgresql.programmi_repository import (
    PostgreSQLVersionedProgrammaFornituraRepository,
)
from ..infrastructure.postgresql.run_tracking_repository import (
    PostgreSQLSchedulingRunRepository,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from ..infrastructure.postgresql.write_plan_validation_repository import (
    PostgreSQLWritePlanValidationRepository,
)
from .settings import ApplicationSettings


@dataclass(frozen=True)
class ApplicationContainer:
    """Grafo completo e immutabile delle dipendenze runtime."""

    settings: ApplicationSettings
    google_gateway: GoogleApiSheetsGateway | None
    programmi_repository: GoogleSheetsProgrammaFornituraRepository | None
    ordini_repository: GoogleSheetsOrdineRepository | None
    scheduling_engine: SchedulingEngine
    run_scheduling: RunScheduling | None
    clock: Clock
    postgresql_settings: PostgreSQLSettings | None = None
    postgresql_connection_factory: PostgreSQLConnectionFactory | None = None
    postgresql_health_check: PostgreSQLHealthCheck | None = None
    postgresql_commit_repository: PostgreSQLCommitRepository | None = None
    application_committer: ApplicationCommitter | None = None
    operational_scheduling_orchestrator: OperationalSchedulingOrchestrator | None = None
    operational_scheduling_entry_point: OperationalSchedulingEntryPoint | None = None


@dataclass(frozen=True)
class _PostgreSQLOperationalComponents:
    connection_factory: PostgreSQLConnectionFactory
    health_check: PostgreSQLHealthCheck
    commit_repository: PostgreSQLCommitRepository
    application_committer: ApplicationCommitter
    orchestrator: OperationalSchedulingOrchestrator
    entry_point: OperationalSchedulingEntryPoint


def _build_container(
    *,
    settings: ApplicationSettings,
    google_service: Any,
    id_generator: IdGenerator,
    postgresql_settings: PostgreSQLSettings | None = None,
    clock: Clock | None = None,
) -> ApplicationContainer:
    clock = clock or SystemClock()
    google_gateway = GoogleApiSheetsGateway(google_service)
    programmi_repository = GoogleSheetsProgrammaFornituraRepository(
        settings.spreadsheet_id,
        google_gateway,
        settings.programmi_fornitura_sheet,
    )
    ordini_repository = GoogleSheetsOrdineRepository(
        settings.spreadsheet_id,
        google_gateway,
        settings.ordini_sheet,
    )
    scheduling_engine = SchedulingEngine()
    run_scheduling = RunScheduling(
        programmi_repository,
        ordini_repository,
        id_generator,
        scheduling_engine,
    )
    operational = (
        _build_postgresql_operational_components(
            postgresql_settings, clock, scheduling_engine
        )
        if postgresql_settings is not None
        else None
    )
    return ApplicationContainer(
        settings=settings,
        google_gateway=google_gateway,
        programmi_repository=programmi_repository,
        ordini_repository=ordini_repository,
        scheduling_engine=scheduling_engine,
        run_scheduling=run_scheduling,
        clock=clock,
        postgresql_settings=postgresql_settings,
        postgresql_connection_factory=(
            operational.connection_factory if operational is not None else None
        ),
        postgresql_health_check=(
            operational.health_check if operational is not None else None
        ),
        postgresql_commit_repository=(
            operational.commit_repository if operational is not None else None
        ),
        application_committer=(
            operational.application_committer if operational is not None else None
        ),
        operational_scheduling_orchestrator=(
            operational.orchestrator if operational is not None else None
        ),
        operational_scheduling_entry_point=(
            operational.entry_point if operational is not None else None
        ),
    )


def _build_operational_container(
    *,
    settings: ApplicationSettings,
    postgresql_settings: PostgreSQLSettings,
    clock: Clock | None = None,
) -> ApplicationContainer:
    """Compone esclusivamente il grafo operativo PostgreSQL."""

    clock = clock or SystemClock()
    scheduling_engine = SchedulingEngine()
    operational = _build_postgresql_operational_components(
        postgresql_settings, clock, scheduling_engine
    )
    return ApplicationContainer(
        settings=settings,
        google_gateway=None,
        programmi_repository=None,
        ordini_repository=None,
        scheduling_engine=scheduling_engine,
        run_scheduling=None,
        clock=clock,
        postgresql_settings=postgresql_settings,
        postgresql_connection_factory=operational.connection_factory,
        postgresql_health_check=operational.health_check,
        postgresql_commit_repository=operational.commit_repository,
        application_committer=operational.application_committer,
        operational_scheduling_orchestrator=operational.orchestrator,
        operational_scheduling_entry_point=operational.entry_point,
    )


def _build_postgresql_operational_components(
    postgresql_settings: PostgreSQLSettings,
    clock: Clock,
    scheduling_engine: SchedulingEngine,
) -> _PostgreSQLOperationalComponents:
    connection_factory = PostgreSQLConnectionFactory(postgresql_settings)
    health_check = PostgreSQLHealthCheck(connection_factory)
    commit_repository = PostgreSQLCommitRepository(connection_factory, clock)
    programmi_repository = PostgreSQLVersionedProgrammaFornituraRepository(
        connection_factory
    )
    ordini_repository = PostgreSQLOrdineRepository(connection_factory)
    identity_repository = PostgreSQLPersistentIdRepository(connection_factory)
    id_allocator = PersistentIdAllocator(identity_repository)
    run_repository = PostgreSQLSchedulingRunRepository(connection_factory)
    run_service = SchedulingRunService(id_allocator, run_repository)
    run_scheduling = RunScheduling(
        programmi_repository,
        ordini_repository,
        id_allocator,
        scheduling_engine,
    )
    write_plan_validator = WritePlanValidator(
        PostgreSQLWritePlanValidationRepository(connection_factory)
    )
    application_committer = ApplicationCommitter(commit_repository)
    execute_scheduling_commit = ExecuteSchedulingCommit(
        run_service,
        WritePlanBuilder(),
        write_plan_validator,
        application_committer,
        clock,
    )
    orchestrator = OperationalSchedulingOrchestrator(
        id_allocator,
        run_service,
        run_scheduling,
        execute_scheduling_commit,
        clock,
    )
    entry_point = OperationalSchedulingEntryPoint(
        OperationalExecutionContextFactory(UuidCorrelationIdGenerator()),
        orchestrator,
    )
    return _PostgreSQLOperationalComponents(
        connection_factory=connection_factory,
        health_check=health_check,
        commit_repository=commit_repository,
        application_committer=application_committer,
        orchestrator=orchestrator,
        entry_point=entry_point,
    )
