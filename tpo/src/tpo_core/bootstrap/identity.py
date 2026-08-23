"""Bootstrap esplicito del commissioning Identity incrementale."""

from ..application.identity.service import IdentityRegistrationCommissioningService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.identity_commissioning import (
    PostgreSQLIdentityRegistrationCommissioningWriter,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_identity_registration_commissioner(
    settings: PostgreSQLSettings,
) -> IdentityRegistrationCommissioningService:
    """Compone il boundary esplicito senza collegarlo allo startup runtime."""

    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return IdentityRegistrationCommissioningService(
        PostgreSQLIdentityRegistrationCommissioningWriter(
            PostgreSQLConnectionFactory(settings)
        )
    )
