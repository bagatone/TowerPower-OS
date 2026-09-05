"""Composition root per Assegnazione Fisica V1 (RegistraAssegnazioneFisica)."""

from ..application.assegnazione_fisica import AssegnazioneFisicaService
from ..infrastructure.postgresql.assegnazione_fisica import PostgreSQLAssegnazioneFisicaWriter
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_assegnazione_fisica_service(settings: PostgreSQLSettings) -> AssegnazioneFisicaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return AssegnazioneFisicaService(
        PostgreSQLAssegnazioneFisicaWriter(PostgreSQLConnectionFactory(settings))
    )
