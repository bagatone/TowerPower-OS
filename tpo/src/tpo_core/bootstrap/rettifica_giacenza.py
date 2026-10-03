"""Composition root for Rettifica Giacenza V1."""

from ..application.rettifica_giacenza import RettificaGiacenzaService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.rettifica_giacenza import PostgreSQLRettificaGiacenzaWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_rettifica_giacenza_service(settings: PostgreSQLSettings) -> RettificaGiacenzaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return RettificaGiacenzaService(
        PostgreSQLRettificaGiacenzaWriter(PostgreSQLConnectionFactory(settings))
    )
