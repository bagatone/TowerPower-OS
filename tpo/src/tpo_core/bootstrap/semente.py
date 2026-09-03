"""Composition root for Semente Commissioning V1."""

from ..application.semente_commissioning import SementeCommissioningService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.semente_commissioning import PostgreSQLSementeCommissioningWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_semente_commissioning_service(
    settings: PostgreSQLSettings,
) -> SementeCommissioningService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return SementeCommissioningService(
        PostgreSQLSementeCommissioningWriter(PostgreSQLConnectionFactory(settings))
    )
