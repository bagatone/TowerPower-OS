"""Composition root for Movimento Carico Raccolta V1 (RegistraCaricoMagazzino)."""

from ..application.movimento_carico import MovimentoCaricoService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.movimento_carico import PostgreSQLMovimentoCaricoWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_movimento_carico_service(settings: PostgreSQLSettings) -> MovimentoCaricoService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return MovimentoCaricoService(
        PostgreSQLMovimentoCaricoWriter(PostgreSQLConnectionFactory(settings))
    )
