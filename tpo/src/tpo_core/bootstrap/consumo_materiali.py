"""Composition root per CONSUMO_MATERIALI_SEMINA V1."""

from ..application.consumo_materiali import ConsumoMaterialiService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.consumo_materiali import PostgreSQLConsumoMaterialiReader
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .movimento_articolo import build_movimento_articolo_service


def build_consumo_materiali_service(settings: PostgreSQLSettings) -> ConsumoMaterialiService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return ConsumoMaterialiService(
        PostgreSQLConsumoMaterialiReader(PostgreSQLConnectionFactory(settings)),
        build_movimento_articolo_service(settings),
    )
