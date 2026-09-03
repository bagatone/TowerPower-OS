"""Bootstrap esplicito del Delivery Fulfilment V1."""

from __future__ import annotations

from ..application.delivery_fulfilment.service import DeliveryFulfilmentService
from ..application.identity.service import PersistentIdAllocator
from ..infrastructure.clock import SystemClock
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.delivery_fulfilment_writer import (
    PostgreSQLDeliveryFulfilmentWriter,
)
from ..infrastructure.postgresql.identity_repository import PostgreSQLPersistentIdRepository
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_delivery_fulfilment_service(
    settings: PostgreSQLSettings,
) -> DeliveryFulfilmentService:
    """Compone il boundary esplicito senza collegarlo allo startup runtime."""

    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    connection_factory = PostgreSQLConnectionFactory(settings)
    return DeliveryFulfilmentService(
        PostgreSQLDeliveryFulfilmentWriter(connection_factory, SystemClock())
    )


def build_delivery_id_allocator(
    settings: PostgreSQLSettings,
) -> PersistentIdAllocator:
    """Compone l'allocatore Identity condiviso per CONSEGNA e MOVIMENTO."""

    if not isinstance(settings, PostgreSQLSettings):
        raise TypeError("settings deve essere PostgreSQLSettings.")
    return PersistentIdAllocator(
        PostgreSQLPersistentIdRepository(
            PostgreSQLConnectionFactory(settings), updated_by="tpo.delivery-fulfilment",
        )
    )
