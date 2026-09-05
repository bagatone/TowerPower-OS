"""Composition root for Disponibilita Commerciale V1 (query a sola lettura)."""

from ..application.disponibilita_commerciale import DisponibilitaCommercialeService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.disponibilita_commerciale import (
    PostgreSQLDisponibilitaCommercialeReader,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_disponibilita_commerciale_service(
    settings: PostgreSQLSettings,
) -> DisponibilitaCommercialeService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return DisponibilitaCommercialeService(
        PostgreSQLDisponibilitaCommercialeReader(PostgreSQLConnectionFactory(settings))
    )
