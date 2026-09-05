"""Composition root for Articolo Commissioning V1 (CommissionArticolo)."""

from ..application.articolo import ArticoloService
from ..infrastructure.postgresql.articolo import PostgreSQLArticoloWriter
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_articolo_service(settings: PostgreSQLSettings) -> ArticoloService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return ArticoloService(
        PostgreSQLArticoloWriter(PostgreSQLConnectionFactory(settings))
    )
