"""Composition root for Fattura Rettifica V1 (RectifyFattura)."""

from ..application.fattura_rettifica import FatturaRettificaService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.fattura_rettifica import PostgreSQLFatturaRettificaWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_fattura_rettifica_service(settings: PostgreSQLSettings) -> FatturaRettificaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return FatturaRettificaService(
        PostgreSQLFatturaRettificaWriter(PostgreSQLConnectionFactory(settings))
    )
