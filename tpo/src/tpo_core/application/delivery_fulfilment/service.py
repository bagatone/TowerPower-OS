"""Caso d'uso Delivery Fulfilment."""

from .errors import InvalidDeliveryCommandError
from .models import DeliveryFulfilmentCommand, DeliveryFulfilmentResult
from .ports import DeliveryFulfilmentWriter


class DeliveryFulfilmentService:
    def __init__(self, writer: DeliveryFulfilmentWriter) -> None:
        self._writer = writer

    def publish(self, command: DeliveryFulfilmentCommand) -> DeliveryFulfilmentResult:
        if not isinstance(command, DeliveryFulfilmentCommand):
            raise InvalidDeliveryCommandError("command non valido.")
        return self._writer.publish(command)
