"""Composition root per FORNITURA/ORDINI/CONSEGNE/ASSEGNAZIONE_FISICA V1."""

from ..application.fornitura_ordini_consegne_lettura import (
    FornituraOrdiniConsegneLetturaService,
)
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.fornitura_ordini_consegne_lettura import (
    PostgreSQLFornituraOrdiniConsegneLetturaReader,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_fornitura_ordini_consegne_lettura_service(
    settings: PostgreSQLSettings,
) -> FornituraOrdiniConsegneLetturaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return FornituraOrdiniConsegneLetturaService(
        PostgreSQLFornituraOrdiniConsegneLetturaReader(PostgreSQLConnectionFactory(settings))
    )
