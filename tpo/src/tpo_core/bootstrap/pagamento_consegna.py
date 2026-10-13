"""Composition root Pagamento Consegna V1."""
from ..application.pagamento_consegna import PagamentoConsegnaService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.pagamento_consegna import PostgreSQLPagamentoConsegnaWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_pagamento_consegna_service(settings: PostgreSQLSettings) -> PagamentoConsegnaService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return PagamentoConsegnaService(
        PostgreSQLPagamentoConsegnaWriter(PostgreSQLConnectionFactory(settings))
    )
