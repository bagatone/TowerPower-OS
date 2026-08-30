"""Composition root Raccolta Recording V1."""
from ..application.raccolta import RaccoltaService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.raccolta import PostgreSQLRaccoltaWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_raccolta_service(settings: PostgreSQLSettings) -> RaccoltaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return RaccoltaService(
        PostgreSQLRaccoltaWriter(PostgreSQLConnectionFactory(settings))
    )
