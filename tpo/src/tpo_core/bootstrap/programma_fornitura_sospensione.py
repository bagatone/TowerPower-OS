"""Composition root PROGRAMMA_FORNITURA Sospensione/Riattivazione V1."""
from ..application.programma_fornitura_sospensione import ProgrammaFornituraSospensioneService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.programma_fornitura_sospensione import (
    PostgreSQLProgrammaFornituraSospensioneWriter,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_programma_fornitura_sospensione_service(
    settings: PostgreSQLSettings,
) -> ProgrammaFornituraSospensioneService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return ProgrammaFornituraSospensioneService(
        PostgreSQLProgrammaFornituraSospensioneWriter(PostgreSQLConnectionFactory(settings))
    )
