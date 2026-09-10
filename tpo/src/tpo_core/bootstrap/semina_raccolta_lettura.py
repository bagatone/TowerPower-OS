"""Composition root per SEMINA/RACCOLTA V1 (query a sola lettura)."""

from ..application.semina_raccolta_lettura import SeminaRaccoltaLetturaService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.semina_raccolta_lettura import (
    PostgreSQLSeminaRaccoltaLetturaReader,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_semina_raccolta_lettura_service(
    settings: PostgreSQLSettings,
) -> SeminaRaccoltaLetturaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return SeminaRaccoltaLetturaService(
        PostgreSQLSeminaRaccoltaLetturaReader(PostgreSQLConnectionFactory(settings))
    )
