"""Composition root per SEMENTE/LOTTO_SEME V1 (query a sola lettura)."""

from ..application.semente_lettura import SementeLetturaService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.semente_lettura import PostgreSQLSementeLetturaReader
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_semente_lettura_service(settings: PostgreSQLSettings) -> SementeLetturaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return SementeLetturaService(
        PostgreSQLSementeLetturaReader(PostgreSQLConnectionFactory(settings))
    )
