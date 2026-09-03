"""Composition root for Semente Impiego Commissioning V1."""

from ..application.semente_impiego_commissioning import SementeImpiegoCommissioningService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.semente_impiego_commissioning import (
    PostgreSQLSementeImpiegoCommissioningWriter,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_semente_impiego_commissioning_service(
    settings: PostgreSQLSettings,
) -> SementeImpiegoCommissioningService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return SementeImpiegoCommissioningService(
        PostgreSQLSementeImpiegoCommissioningWriter(PostgreSQLConnectionFactory(settings))
    )
