"""Composition root per la BOLLA DI CONSEGNA V1 (query a sola lettura)."""

from ..application.bolla_lettura import BollaLetturaService
from ..infrastructure.postgresql.bolla_lettura import PostgreSQLBollaLetturaReader
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_bolla_lettura_service(settings: PostgreSQLSettings) -> BollaLetturaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return BollaLetturaService(
        PostgreSQLBollaLetturaReader(PostgreSQLConnectionFactory(settings))
    )
