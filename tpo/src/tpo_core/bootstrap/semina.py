"""Composition root Semina Commissioning V1."""
from ..application.semina_commissioning import SeminaCommissioningService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.semina_commissioning import PostgreSQLSeminaCommissioningWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_semina_commissioning_service(settings: PostgreSQLSettings) -> SeminaCommissioningService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return SeminaCommissioningService(
        PostgreSQLSeminaCommissioningWriter(PostgreSQLConnectionFactory(settings))
    )
