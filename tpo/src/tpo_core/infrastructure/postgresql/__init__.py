"""Primitive infrastrutturali PostgreSQL, indipendenti dal provider."""

from .connection import PostgreSQLConnectionFactory
from .errors import (
    InvalidPostgreSQLSettingsError,
    PostgreSQLConnectionError,
    PostgreSQLError,
    PostgreSQLHealthCheckError,
)
from .health import PostgreSQLHealthCheck, PostgreSQLHealthResult
from .identity_repository import PostgreSQLPersistentIdRepository
from .run_tracking_repository import PostgreSQLSchedulingRunRepository
from .settings import PostgreSQLSettings

__all__ = [
    "InvalidPostgreSQLSettingsError",
    "PostgreSQLConnectionError",
    "PostgreSQLConnectionFactory",
    "PostgreSQLError",
    "PostgreSQLHealthCheck",
    "PostgreSQLHealthCheckError",
    "PostgreSQLHealthResult",
    "PostgreSQLPersistentIdRepository",
    "PostgreSQLSchedulingRunRepository",
    "PostgreSQLSettings",
]
