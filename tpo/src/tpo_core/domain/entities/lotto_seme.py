"""Entità LOTTO_SEME del Core Domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..errors import InvalidQuantityError, InvariantViolationError
from ..identifiers import LottoSemeId
from ..quantities import Quantity, UnitOfMeasure


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvariantViolationError(f"LOTTO_SEME richiede {name} normalizzato non vuoto.")


@dataclass(frozen=True)
class LottoSeme:
    """Lotto fisico permanente di seme realmente disponibile o impiegabile."""

    id: LottoSemeId
    seed_supplier: str
    seed_commercial_reference: str
    manufacturer_lot_number: str
    received_date: date
    expiry_date: date | None
    initial_quantity: Quantity
    remaining_quantity: Quantity
    anomaly: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, LottoSemeId):
            raise InvariantViolationError("LOTTO_SEME richiede un LottoSemeId valido.")
        for name, value in (
            ("fornitore", self.seed_supplier),
            ("referenza commerciale", self.seed_commercial_reference),
            ("numero lotto produttore", self.manufacturer_lot_number),
        ):
            _text(name, value)
        if not isinstance(self.received_date, date):
            raise InvariantViolationError("LOTTO_SEME richiede una data ricezione esatta.")
        if self.expiry_date is not None:
            if not isinstance(self.expiry_date, date):
                raise InvariantViolationError("data scadenza LOTTO_SEME non valida.")
            if self.expiry_date < self.received_date:
                raise InvariantViolationError("La scadenza non può precedere la ricezione.")
        for name, quantity in (
            ("quantità iniziale", self.initial_quantity),
            ("quantità residua", self.remaining_quantity),
        ):
            if not isinstance(quantity, Quantity) or quantity.unit is not UnitOfMeasure.GRAM:
                raise InvalidQuantityError(f"{name} LOTTO_SEME deve essere espressa in GRAM.")
        if self.initial_quantity.value <= 0:
            raise InvalidQuantityError("La quantità iniziale deve essere positiva.")
        if self.remaining_quantity.value < 0:
            raise InvalidQuantityError("La quantità residua non può essere negativa.")
        if self.remaining_quantity.value > self.initial_quantity.value:
            raise InvalidQuantityError("La quantità residua non può superare quella iniziale.")
        if self.anomaly is not None:
            _text("anomalia", self.anomaly)

    @property
    def consumed_quantity(self) -> Quantity:
        return Quantity(
            Decimal(self.initial_quantity.value - self.remaining_quantity.value),
            UnitOfMeasure.GRAM,
        )
