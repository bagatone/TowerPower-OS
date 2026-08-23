"""Composition root for operational-data onboarding."""

from ..application.onboarding.service import OperationalDataOnboardingService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.onboarding import PostgreSQLOperationalDataOnboardingWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_operational_data_onboarding_service(
    settings: PostgreSQLSettings,
) -> OperationalDataOnboardingService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return OperationalDataOnboardingService(
        PostgreSQLOperationalDataOnboardingWriter(PostgreSQLConnectionFactory(settings))
    )
