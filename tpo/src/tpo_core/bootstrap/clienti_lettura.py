"""Composition root per CLIENTI V1 (query a sola lettura)."""

from ..application.clienti_lettura import ClientiLetturaService
from ..infrastructure.postgresql.clienti_lettura import PostgreSQLClientiLetturaReader
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_clienti_lettura_service(settings: PostgreSQLSettings) -> ClientiLetturaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return ClientiLetturaService(
        PostgreSQLClientiLetturaReader(PostgreSQLConnectionFactory(settings))
    )
