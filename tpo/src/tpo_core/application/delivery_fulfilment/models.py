"""Contratto provider-neutral del Delivery Fulfilment Writer V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from ...domain.identifiers import (
    ActorId,
    ClienteId,
    ConsegnaId,
    MovimentoId,
    OrdineId,
)
from ...domain.quantities import UnitOfMeasure
from ...domain.time_reference import CurrentSystemDate
from .errors import InvalidDeliveryCommandError


def _text(name: str, value: str | None, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidDeliveryCommandError(f"{name} deve essere testo non vuoto e normalizzato.")


def _version(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvalidDeliveryCommandError(f"{name} deve essere un intero non negativo.")


def _signed_quantity(value: Decimal) -> Decimal:
    if isinstance(value, (float, bool)):
        raise InvalidDeliveryCommandError("quantity non accetta float o booleani.")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidDeliveryCommandError("quantity deve essere decimale.") from exc
    if not result.is_finite() or result == 0 or result.as_tuple().exponent < -6:
        raise InvalidDeliveryCommandError("quantity deve essere non zero con massimo sei decimali.")
    return result


@dataclass(frozen=True)
class DeliveryLineReference:
    """Identità operativa congelata di una RIGA_CONSEGNA."""

    delivery_id: ConsegnaId
    position: int

    def __post_init__(self) -> None:
        if not isinstance(self.delivery_id, ConsegnaId):
            raise InvalidDeliveryCommandError("delivery_id originale non valido.")
        if not isinstance(self.position, int) or isinstance(self.position, bool) or self.position <= 0:
            raise InvalidDeliveryCommandError("position originale deve essere positiva.")


@dataclass(frozen=True)
class DeliveryFulfilmentLine:
    """Delta commerciale richiesto per una singola RIGA_ORDINE."""

    order_id: OrdineId
    order_line_id: str
    quantity: Decimal
    unit: UnitOfMeasure
    expected_order_version: int
    expected_order_line_version: int
    movement_id: MovimentoId | None = None
    correction_of: DeliveryLineReference | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.order_id, OrdineId):
            raise InvalidDeliveryCommandError("order_id non valido.")
        _text("order_line_id", self.order_line_id)
        if not self.order_line_id.startswith("RO-"):
            raise InvalidDeliveryCommandError("order_line_id deve essere un RO-*.")
        object.__setattr__(self, "quantity", _signed_quantity(self.quantity))
        if not isinstance(self.unit, UnitOfMeasure):
            raise InvalidDeliveryCommandError("unit non valida.")
        _version("expected_order_version", self.expected_order_version)
        _version("expected_order_line_version", self.expected_order_line_version)
        if self.correction_of is None:
            if self.quantity <= 0 or not isinstance(self.movement_id, MovimentoId):
                raise InvalidDeliveryCommandError(
                    "Una riga ordinaria richiede quantity positiva e movement_id."
                )
        elif self.movement_id is not None:
            raise InvalidDeliveryCommandError("Una rettifica commerciale non ammette movement_id.")

    @property
    def is_correction(self) -> bool:
        return self.correction_of is not None


@dataclass(frozen=True)
class DeliveryFulfilmentCommand:
    """Pubblicazione atomica di una CONSEGNA effettiva."""

    delivery_id: ConsegnaId
    client_id: ClienteId
    planned_date: date
    effective_at: datetime
    lines: tuple[DeliveryFulfilmentLine, ...]
    actor: ActorId
    reason: str
    correlation_id: str
    operator: str | None = None
    physical_destination: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.delivery_id, ConsegnaId):
            raise InvalidDeliveryCommandError("delivery_id non valido.")
        if not isinstance(self.client_id, ClienteId):
            raise InvalidDeliveryCommandError("client_id non valido.")
        if not isinstance(self.planned_date, date) or isinstance(self.planned_date, datetime):
            raise InvalidDeliveryCommandError("planned_date non valida.")
        object.__setattr__(self, "effective_at", CurrentSystemDate(self.effective_at).datetime)
        if not isinstance(self.lines, tuple) or not self.lines:
            raise InvalidDeliveryCommandError("lines deve essere una tuple non vuota.")
        if any(not isinstance(line, DeliveryFulfilmentLine) for line in self.lines):
            raise InvalidDeliveryCommandError("lines contiene elementi non validi.")
        if len({line.order_line_id for line in self.lines}) != len(self.lines):
            raise InvalidDeliveryCommandError("Ogni RIGA_ORDINE può variare una sola volta per command.")
        if not isinstance(self.actor, ActorId):
            raise InvalidDeliveryCommandError("actor non valido.")
        _text("reason", self.reason)
        _text("correlation_id", self.correlation_id)
        _text("operator", self.operator, optional=True)
        _text("physical_destination", self.physical_destination, optional=True)

    @property
    def is_correction(self) -> bool:
        kinds = {line.is_correction for line in self.lines}
        if len(kinds) != 1:
            raise InvalidDeliveryCommandError(
                "Una CONSEGNA non può mescolare righe ordinarie e correttive."
            )
        return kinds.pop()


@dataclass(frozen=True)
class DeliveryFulfilmentResult:
    delivery_id: ConsegnaId
    order_states: tuple[tuple[OrdineId, str], ...]
    delivery_line_count: int
    movement_count: int
