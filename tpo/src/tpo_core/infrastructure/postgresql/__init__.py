"""Primitive infrastrutturali PostgreSQL, indipendenti dal provider."""

from .connection import PostgreSQLConnectionFactory
from .commit_repository import PostgreSQLCommitRepository
from .errors import (
    InvalidPostgreSQLSettingsError,
    PostgreSQLConnectionError,
    PostgreSQLError,
    PostgreSQLHealthCheckError,
)
from .health import PostgreSQLHealthCheck, PostgreSQLHealthResult
from .identity_repository import PostgreSQLPersistentIdRepository
from .orders_repository import PostgreSQLOrdineRepository
from .programmi_repository import PostgreSQLVersionedProgrammaFornituraRepository
from .production_planning_identity import PostgreSQLProductionPlanningIdentityAdapter
from .run_tracking_repository import PostgreSQLSchedulingRunRepository
from .settings import PostgreSQLSettings
from .write_plan_validation_repository import PostgreSQLWritePlanValidationRepository

__all__ = [
    "InvalidPostgreSQLSettingsError",
    "PostgreSQLConnectionError",
    "PostgreSQLConnectionFactory",
    "PostgreSQLCommitRepository",
    "PostgreSQLError",
    "PostgreSQLHealthCheck",
    "PostgreSQLHealthCheckError",
    "PostgreSQLHealthResult",
    "PostgreSQLPersistentIdRepository",
    "PostgreSQLOrdineRepository",
    "PostgreSQLProductionPlanningIdentityAdapter",
    "PostgreSQLVersionedProgrammaFornituraRepository",
    "PostgreSQLSchedulingRunRepository",
    "PostgreSQLSettings",
    "PostgreSQLWritePlanValidationRepository",
]
