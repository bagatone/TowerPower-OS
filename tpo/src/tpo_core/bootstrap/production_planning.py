"""Official composition root for the PostgreSQL Production Planning runtime."""

from __future__ import annotations

import os
from typing import Mapping

from ..application.identity.service import PersistentIdAllocator
from ..application.agronomic_commissioning.service import AgronomicProtocolCommissioningService
from ..application.ports.clock import Clock
from ..application.production_planning.assembler import ProductionPlanningCommitAssembler
from ..application.production_planning.engine import ProductionPlanningEngine
from ..application.production_planning.service import ProductionPlanningService
from ..application.policy_commissioning.service import (
    ProductionPlanningPolicyCommissioningService,
)
from ..infrastructure.clock import SystemClock
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.agronomic_commissioning import PostgreSQLAgronomicProtocolCommissioningWriter
from ..infrastructure.postgresql.identity_repository import PostgreSQLPersistentIdRepository
from ..infrastructure.postgresql.production_planning_commit_writer import (
    PostgreSQLProductionPlanningCommitWriter,
)
from ..infrastructure.postgresql.production_planning_identity import (
    PostgreSQLProductionPlanningIdentityAdapter,
)
from ..infrastructure.postgresql.production_planning_input import (
    PostgreSQLProductionPlanningInputAdapter,
)
from ..infrastructure.postgresql.production_planning_policy_commissioning import (
    PostgreSQLProductionPlanningPolicyCommissioningWriter,
)
from ..infrastructure.postgresql.production_planning_run import (
    PostgreSQLProductionPlanningRunAdapter,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings


class _ProductionPlanningClockAdapter:
    """Projects the official TPO Clock value onto PlanningClockPort."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def now(self):
        return self._clock.now().datetime


def build_production_planning_runtime(
    postgresql_settings: PostgreSQLSettings,
    *,
    clock: Clock | None = None,
) -> ProductionPlanningService:
    """Compose a new lazy, fully wired Production Planning service."""

    if not isinstance(postgresql_settings, PostgreSQLSettings):
        raise TypeError("postgresql_settings deve essere PostgreSQLSettings.")
    official_clock = clock or SystemClock()
    connection_factory = PostgreSQLConnectionFactory(postgresql_settings)
    identity = PostgreSQLProductionPlanningIdentityAdapter(
        PersistentIdAllocator(
            PostgreSQLPersistentIdRepository(
                connection_factory, updated_by="tpo.production-planning",
            )
        )
    )
    return ProductionPlanningService(
        identity=identity,
        inputs=PostgreSQLProductionPlanningInputAdapter(connection_factory),
        runs=PostgreSQLProductionPlanningRunAdapter(connection_factory),
        commit=PostgreSQLProductionPlanningCommitWriter(connection_factory),
        clock=_ProductionPlanningClockAdapter(official_clock),
        engine=ProductionPlanningEngine(),
        assembler=ProductionPlanningCommitAssembler(),
    )


def build_production_planning_runtime_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    clock: Clock | None = None,
) -> ProductionPlanningService:
    """Load only the official PostgreSQL environment and compose the runtime."""

    source = os.environ if environment is None else environment
    return build_production_planning_runtime(
        PostgreSQLSettings.from_environment(source), clock=clock,
    )


def build_production_planning_policy_commissioner(
    postgresql_settings: PostgreSQLSettings,
    *,
    clock: Clock | None = None,
) -> ProductionPlanningPolicyCommissioningService:
    """Compose the explicit PostgreSQL policy commissioning authority."""

    if not isinstance(postgresql_settings, PostgreSQLSettings):
        raise TypeError("postgresql_settings deve essere PostgreSQLSettings.")
    official_clock = clock or SystemClock()
    connection_factory = PostgreSQLConnectionFactory(postgresql_settings)
    return ProductionPlanningPolicyCommissioningService(
        writer=PostgreSQLProductionPlanningPolicyCommissioningWriter(
            connection_factory,
        ),
        clock=official_clock,
    )


def build_agronomic_protocol_commissioner(
    postgresql_settings: PostgreSQLSettings,
    *,
    clock: Clock | None = None,
) -> AgronomicProtocolCommissioningService:
    """Compose the explicit PostgreSQL agronomic commissioning authority."""
    if not isinstance(postgresql_settings, PostgreSQLSettings):
        raise TypeError("postgresql_settings deve essere PostgreSQLSettings.")
    factory = PostgreSQLConnectionFactory(postgresql_settings)
    return AgronomicProtocolCommissioningService(
        writer=PostgreSQLAgronomicProtocolCommissioningWriter(factory),
        clock=clock or SystemClock(),
    )
