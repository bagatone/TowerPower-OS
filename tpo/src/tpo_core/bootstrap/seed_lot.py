"""Composition root for Seed Lot Commissioning V1."""

from ..application.seed_lot_commissioning import SeedLotCommissioningService
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.seed_lot_commissioning import PostgreSQLSeedLotCommissioningWriter
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_seed_lot_commissioning_service(
    settings: PostgreSQLSettings,
) -> SeedLotCommissioningService:
    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return SeedLotCommissioningService(
        PostgreSQLSeedLotCommissioningWriter(PostgreSQLConnectionFactory(settings))
    )
