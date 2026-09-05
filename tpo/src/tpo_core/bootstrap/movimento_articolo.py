"""Composition root for Movimento Articolo V1 (RegistraMovimentoArticolo)."""

from ..application.movimento_articolo import MovimentoArticoloService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.movimento_articolo import (
    PostgreSQLMovimentoArticoloWriter,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_movimento_articolo_service(
    settings: PostgreSQLSettings,
) -> MovimentoArticoloService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return MovimentoArticoloService(
        PostgreSQLMovimentoArticoloWriter(PostgreSQLConnectionFactory(settings))
    )
