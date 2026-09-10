"""Composition root per RUN/RUN_LOG V1 (query a sola lettura)."""

from ..application.run_lettura import RunLetturaService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.run_lettura import PostgreSQLRunLetturaReader
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_run_lettura_service(settings: PostgreSQLSettings) -> RunLetturaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return RunLetturaService(
        PostgreSQLRunLetturaReader(PostgreSQLConnectionFactory(settings))
    )
