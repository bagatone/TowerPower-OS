"""Quantità e unità di misura condivise dal Core Domain."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from .errors import InvalidQuantityError, InvalidUnitOfMeasureError, InvariantViolationError


class UnitOfMeasure(str, Enum):
    SET = "SET"
    GRAM = "GRAM"
    UNIT = "UNIT"


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    unit: UnitOfMeasure

    def __post_init__(self) -> None:
        if not isinstance(self.unit, UnitOfMeasure):
            raise InvalidUnitOfMeasureError("L'unità di misura è obbligatoria e deve essere ufficiale.")
        if isinstance(self.value, (float, bool)):
            raise InvalidQuantityError("La quantità non accetta valori float o booleani.")

        try:
            parsed = self.value if isinstance(self.value, Decimal) else Decimal(self.value)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise InvalidQuantityError(f"Quantità non numerica: {self.value!r}.") from exc

        if not parsed.is_finite():
            raise InvalidQuantityError("La quantità deve essere finita.")
        if parsed < 0:
            raise InvalidQuantityError("La quantità non può essere negativa.")

        object.__setattr__(self, "value", parsed)

    def __add__(self, other: object) -> Quantity:
        if not isinstance(other, Quantity):
            return NotImplemented
        compatible = self._compatible(other)
        return Quantity(self.value + compatible.value, self.unit)

    def __sub__(self, other: object) -> Quantity:
        if not isinstance(other, Quantity):
            return NotImplemented
        compatible = self._compatible(other)
        result = self.value - compatible.value
        if result < 0:
            raise InvariantViolationError("La sottrazione non può produrre una quantità negativa.")
        return Quantity(result, self.unit)

    def _compatible(self, other: object) -> Quantity:
        if not isinstance(other, Quantity):
            return NotImplemented
        if self.unit is not other.unit:
            raise InvalidUnitOfMeasureError(
                f"Unità incompatibili: {self.unit.value} e {other.unit.value}."
            )
        return other
