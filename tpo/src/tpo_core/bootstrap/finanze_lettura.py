"""Composition root per FINANZE V1 (query a sola lettura: FATTURA/INCASSO/USCITA)."""

from ..application.finanze_lettura import FinanzeLetturaService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.finanze_lettura import PostgreSQLFinanzeLetturaReader
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_finanze_lettura_service(settings: PostgreSQLSettings) -> FinanzeLetturaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return FinanzeLetturaService(
        PostgreSQLFinanzeLetturaReader(PostgreSQLConnectionFactory(settings))
    )
