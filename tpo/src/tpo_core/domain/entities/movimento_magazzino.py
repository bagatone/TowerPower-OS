"""Entità MOVIMENTO_MAGAZZINO del Core Domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..errors import InvalidQuantityError, InvariantViolationError
from ..identifiers import MovimentoId, VarietaId
from ..quantities import Quantity
from ..states import MovimentoDirection, MovimentoType
from ..time_reference import CurrentSystemDate


@dataclass(frozen=True, eq=False)
class MovimentoMagazzino:
    """Evento storico autorizzato che determina una variazione dello STOCK."""

    id: MovimentoId
    varieta_id: VarietaId
    tipo: MovimentoType
    direzione: MovimentoDirection
    quantita: Quantity
    data_movimento: datetime
    motivo: str
    origine: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, MovimentoId):
            raise InvariantViolationError(
                "MOVIMENTO_MAGAZZINO richiede un MovimentoId valido."
            )
        if not isinstance(self.varieta_id, VarietaId):
            raise InvariantViolationError(
                "MOVIMENTO_MAGAZZINO richiede un riferimento VarietaId valido."
            )
        if not isinstance(self.tipo, MovimentoType):
            raise InvariantViolationError(
                "MOVIMENTO_MAGAZZINO richiede un MovimentoType ufficiale."
            )
        if not isinstance(self.direzione, MovimentoDirection):
            raise InvariantViolationError(
                "MOVIMENTO_MAGAZZINO richiede una MovimentoDirection ufficiale."
            )
        if not isinstance(self.quantita, Quantity):
            raise InvalidQuantityError(
                "MOVIMENTO_MAGAZZINO richiede una quantità valida."
            )
        if self.quantita.value <= 0:
            raise InvalidQuantityError(
                "La quantità del MOVIMENTO_MAGAZZINO deve essere maggiore di zero."
            )

        object.__setattr__(
            self,
            "data_movimento",
            CurrentSystemDate(self.data_movimento).datetime,
        )

        for nome, valore in (("motivo", self.motivo), ("origine", self.origine)):
            if not isinstance(valore, str) or not valore.strip():
                raise InvariantViolationError(
                    f"MOVIMENTO_MAGAZZINO richiede {nome} non vuoto."
                )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, MovimentoMagazzino):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
