"""Composition root Semina Lifecycle Event Authority V1."""
from ..application.semina_lifecycle import SeminaLifecycleService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.semina_lifecycle import PostgreSQLSeminaLifecycleWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_semina_lifecycle_service(settings: PostgreSQLSettings) -> SeminaLifecycleService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return SeminaLifecycleService(
        PostgreSQLSeminaLifecycleWriter(PostgreSQLConnectionFactory(settings))
    )
