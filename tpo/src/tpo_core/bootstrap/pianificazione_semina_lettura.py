"""Composition root per "Da seminare" V1 (query a sola lettura)."""

from ..application.pianificazione_semina_lettura import PianificazioneSeminaLetturaService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.pianificazione_semina_lettura import (
    PostgreSQLPianificazioneSeminaLetturaReader,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_pianificazione_semina_lettura_service(
    settings: PostgreSQLSettings,
) -> PianificazioneSeminaLetturaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return PianificazioneSeminaLetturaService(
        PostgreSQLPianificazioneSeminaLetturaReader(PostgreSQLConnectionFactory(settings))
    )
