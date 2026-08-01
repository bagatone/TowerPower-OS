"""Entità e Value Object del dominio CONSEGNE."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from ..errors import InvalidQuantityError, InvariantViolationError
from ..identifiers import ClienteId, ConsegnaId, OrdineId, VarietaId
from ..quantities import Quantity
from ..states import ConsegnaState
from ..time_reference import CurrentSystemDate


@dataclass(frozen=True)
class RigaConsegna:
    """Quantità di prodotto effettivamente consegnata per una VARIETA."""

    varieta_id: VarietaId
    quantita: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvariantViolationError("La riga CONSEGNA richiede un VarietaId valido.")
        if not isinstance(self.quantita, Quantity):
            raise InvalidQuantityError("La riga CONSEGNA richiede una quantità valida.")
        if self.quantita.value <= 0:
            raise InvalidQuantityError(
                "La quantità della riga CONSEGNA deve essere maggiore di zero."
            )


@dataclass(frozen=True, eq=False)
class Consegna:
    """Evento logistico di consegna del prodotto a un CLIENTE."""

    id: ConsegnaId
    cliente_id: ClienteId
    ordine_ids: tuple[OrdineId, ...]
    righe: tuple[RigaConsegna, ...]
    stato: ConsegnaState
    data_prevista: date
    data_effettiva: datetime | None = None
    motivazione: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, ConsegnaId):
            raise InvariantViolationError("CONSEGNA richiede un ConsegnaId valido.")
        if not isinstance(self.cliente_id, ClienteId):
            raise InvariantViolationError("CONSEGNA richiede un riferimento ClienteId valido.")
        if not isinstance(self.ordine_ids, tuple):
            raise InvariantViolationError("I riferimenti agli ORDINI devono essere una tuple.")
        if any(not isinstance(ordine_id, OrdineId) for ordine_id in self.ordine_ids):
            raise InvariantViolationError(
                "I riferimenti agli ORDINI richiedono esclusivamente OrdineId validi."
            )
        if len(set(self.ordine_ids)) != len(self.ordine_ids):
            raise InvariantViolationError("Gli OrdineId della CONSEGNA non possono essere duplicati.")
        if not isinstance(self.righe, tuple) or not self.righe:
            raise InvariantViolationError("CONSEGNA richiede almeno una riga in una tuple.")
        if any(not isinstance(riga, RigaConsegna) for riga in self.righe):
            raise InvariantViolationError("CONSEGNA accetta esclusivamente righe valide.")
        if not isinstance(self.stato, ConsegnaState):
            raise InvariantViolationError("CONSEGNA richiede uno stato ufficiale ConsegnaState.")
        if not isinstance(self.data_prevista, date) or isinstance(self.data_prevista, datetime):
            raise InvariantViolationError("CONSEGNA richiede una data_prevista valida.")
        if self.data_effettiva is not None:
            object.__setattr__(
                self,
                "data_effettiva",
                CurrentSystemDate(self.data_effettiva).datetime,
            )
        if not self.ordine_ids:
            if not isinstance(self.motivazione, str) or not self.motivazione.strip():
                raise InvariantViolationError(
                    "Una CONSEGNA senza ORDINE richiede una motivazione non vuota."
                )
        elif self.motivazione is not None and (
            not isinstance(self.motivazione, str) or not self.motivazione.strip()
        ):
            raise InvariantViolationError(
                "La motivazione, se presente, deve essere una stringa non vuota."
            )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Consegna):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
