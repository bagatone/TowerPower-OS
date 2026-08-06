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
from .run_tracking_repository import PostgreSQLSchedulingRunRepository
from .settings import PostgreSQLSettings

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
    "PostgreSQLSchedulingRunRepository",
    "PostgreSQLSettings",
]
