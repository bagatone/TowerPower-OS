"""Entità VARIETA del Core Domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..errors import InvariantViolationError
from ..identifiers import VarietaId
from ..states import VarietaState


@dataclass(frozen=True, eq=False)
class Varieta:
    """Identità produttiva generale di una coltura."""

    id: VarietaId
    denominazione: str
    stato: VarietaState

    def __post_init__(self) -> None:
        if not isinstance(self.id, VarietaId):
            raise InvariantViolationError("VARIETA richiede un VarietaId valido.")
        if not isinstance(self.denominazione, str) or not self.denominazione.strip():
            raise InvariantViolationError(
                "La denominazione ufficiale di VARIETA deve essere una stringa non vuota."
            )
        if not isinstance(self.stato, VarietaState):
            raise InvariantViolationError("VARIETA richiede uno stato ufficiale VarietaState.")

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Varieta):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
