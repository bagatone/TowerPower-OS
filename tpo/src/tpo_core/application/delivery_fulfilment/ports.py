"""Porta dell'unico writer Delivery Fulfilment."""

from typing import Protocol

from .models import DeliveryFulfilmentCommand, DeliveryFulfilmentResult


class DeliveryFulfilmentWriter(Protocol):
    def publish(self, command: DeliveryFulfilmentCommand) -> DeliveryFulfilmentResult:
        """Pubblica commercial e physical facts nel medesimo commit."""
        ...
