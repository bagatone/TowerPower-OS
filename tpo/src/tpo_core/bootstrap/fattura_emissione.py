"""Composition root for Fattura Emissione V1."""

from ..application.fattura_emissione import FatturaEmissioneService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.fattura_emissione import PostgreSQLFatturaEmissioneWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_fattura_emissione_service(settings: PostgreSQLSettings) -> FatturaEmissioneService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return FatturaEmissioneService(
        PostgreSQLFatturaEmissioneWriter(PostgreSQLConnectionFactory(settings))
    )
