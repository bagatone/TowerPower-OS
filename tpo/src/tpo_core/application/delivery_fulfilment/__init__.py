"""API applicativa del Delivery Fulfilment Writer."""

from .errors import (
    DeliveryAlreadyPublishedError,
    DeliveryCommitError,
    DeliveryCommitOutcomeUncertain,
    DeliveryConcurrencyError,
    DeliveryFulfilmentError,
    DeliveryValidationError,
    InvalidDeliveryCommandError,
)
from .models import (
    DeliveryFulfilmentCommand,
    DeliveryFulfilmentLine,
    DeliveryFulfilmentResult,
    DeliveryLineReference,
)
from .ports import DeliveryFulfilmentWriter
from .service import DeliveryFulfilmentService

__all__ = [
    "DeliveryAlreadyPublishedError", "DeliveryCommitError",
    "DeliveryCommitOutcomeUncertain", "DeliveryConcurrencyError",
    "DeliveryFulfilmentCommand", "DeliveryFulfilmentError",
    "DeliveryFulfilmentLine", "DeliveryFulfilmentResult",
    "DeliveryFulfilmentService", "DeliveryFulfilmentWriter",
    "DeliveryLineReference", "DeliveryValidationError",
    "InvalidDeliveryCommandError",
]
