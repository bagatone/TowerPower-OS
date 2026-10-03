"""Composition root for Ordine Manuale V1."""

from ..application.ordine_manuale import OrdineManualeService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.ordine_manuale import PostgreSQLOrdineManualeWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_ordine_manuale_service(settings: PostgreSQLSettings) -> OrdineManualeService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return OrdineManualeService(
        PostgreSQLOrdineManualeWriter(PostgreSQLConnectionFactory(settings))
    )
