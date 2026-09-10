"""Composition root per VARIETA/LISTINO_VARIETA V1 (query a sola lettura)."""

from ..application.varieta_lettura import VarietaLetturaService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from ..infrastructure.postgresql.varieta_lettura import PostgreSQLVarietaLetturaReader


def build_varieta_lettura_service(settings: PostgreSQLSettings) -> VarietaLetturaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return VarietaLetturaService(
        PostgreSQLVarietaLetturaReader(PostgreSQLConnectionFactory(settings))
    )
