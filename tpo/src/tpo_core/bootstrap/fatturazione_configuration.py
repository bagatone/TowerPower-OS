"""Composition root dei writer di Configuration fatturazione (LISTINO_VARIETA, CLIENTE)."""

from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.fatturazione_configuration import (
    PostgreSQLClienteFatturazioneWriter,
    PostgreSQLListinoVarietaWriter,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_listino_varieta_writer(settings: PostgreSQLSettings) -> PostgreSQLListinoVarietaWriter:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return PostgreSQLListinoVarietaWriter(PostgreSQLConnectionFactory(settings))


def build_cliente_fatturazione_writer(settings: PostgreSQLSettings) -> PostgreSQLClienteFatturazioneWriter:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return PostgreSQLClienteFatturazioneWriter(PostgreSQLConnectionFactory(settings))
