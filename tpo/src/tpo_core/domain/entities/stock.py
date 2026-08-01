"""Rappresentazione STOCK del Core Domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..errors import InvalidQuantityError, InvariantViolationError
from ..identifiers import VarietaId
from ..quantities import Quantity
from ..time_reference import CurrentSystemDate


@dataclass(frozen=True, eq=False)
class Stock:
    """Fotografia corrente della disponibilità operativa di una VARIETA."""

    varieta_id: VarietaId
    disponibile: Quantity
    ultimo_aggiornamento: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvariantViolationError("STOCK richiede un riferimento VarietaId valido.")
        if not isinstance(self.disponibile, Quantity):
            raise InvalidQuantityError("STOCK richiede una quantità disponibile valida.")
        if self.disponibile.value < 0:
            raise InvalidQuantityError("La disponibilità dello STOCK non può essere negativa.")
        if self.ultimo_aggiornamento is not None:
            object.__setattr__(
                self,
                "ultimo_aggiornamento",
                CurrentSystemDate(self.ultimo_aggiornamento).datetime,
            )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Stock):
            return NotImplemented
        return self.varieta_id == other.varieta_id

    def __hash__(self) -> int:
        return hash(self.varieta_id)
