"""Entità RACCOLTA del Core Domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..errors import InvalidQuantityError, InvariantViolationError
from ..identifiers import RaccoltaId, SeminaId
from ..quantities import Quantity, UnitOfMeasure
from ..time_reference import CurrentSystemDate


@dataclass(frozen=True, eq=False)
class Raccolta:
    """Evento storico di prelievo di prodotto da una SEMINA."""

    id: RaccoltaId
    semina_id: SeminaId
    data_raccolta: datetime
    quantita: Quantity
    operatore: str | None = None
    destinazione_prevista: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, RaccoltaId):
            raise InvariantViolationError("RACCOLTA richiede un RaccoltaId valido.")
        if not isinstance(self.semina_id, SeminaId):
            raise InvariantViolationError("RACCOLTA richiede un riferimento SeminaId valido.")

        object.__setattr__(
            self,
            "data_raccolta",
            CurrentSystemDate(self.data_raccolta).datetime,
        )

        if not isinstance(self.quantita, Quantity):
            raise InvalidQuantityError("RACCOLTA richiede una quantità valida.")
        if self.quantita.unit is not UnitOfMeasure.SET:
            raise InvalidQuantityError("La quantità della RACCOLTA deve essere espressa in SET.")
        if self.quantita.value <= 0:
            raise InvalidQuantityError("La quantità della RACCOLTA deve essere maggiore di zero.")

        for nome, valore in (
            ("operatore", self.operatore),
            ("destinazione prevista", self.destinazione_prevista),
            ("note", self.note),
        ):
            if valore is not None and (not isinstance(valore, str) or not valore.strip()):
                raise InvariantViolationError(
                    f"Il campo facoltativo {nome} deve essere una stringa non vuota."
                )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Raccolta):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
