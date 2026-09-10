"""Composition root per MAGAZZINO V1 (query a sola lettura)."""

from ..application.magazzino_lettura import MagazzinoLetturaService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.magazzino_lettura import PostgreSQLMagazzinoLetturaReader
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_magazzino_lettura_service(settings: PostgreSQLSettings) -> MagazzinoLetturaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return MagazzinoLetturaService(
        PostgreSQLMagazzinoLetturaReader(PostgreSQLConnectionFactory(settings))
    )
