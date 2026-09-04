"""Composition root Uscita Recording V1."""
from ..application.uscita import UscitaService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from ..infrastructure.postgresql.uscita import PostgreSQLUscitaWriter


def build_uscita_service(settings: PostgreSQLSettings) -> UscitaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return UscitaService(
        PostgreSQLUscitaWriter(PostgreSQLConnectionFactory(settings))
    )
