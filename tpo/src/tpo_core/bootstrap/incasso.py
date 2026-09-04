"""Composition root Incasso Recording V1."""
from ..application.incasso import IncassoService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.incasso import PostgreSQLIncassoWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_incasso_service(settings: PostgreSQLSettings) -> IncassoService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return IncassoService(
        PostgreSQLIncassoWriter(PostgreSQLConnectionFactory(settings))
    )
