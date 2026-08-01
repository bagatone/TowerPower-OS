"""Entità SEMINA del Core Domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..errors import InvalidQuantityError, InvariantViolationError
from ..identifiers import SeminaId, VarietaId
from ..quantities import Quantity, UnitOfMeasure
from ..states import SeminaState
from ..time_reference import CurrentSystemDate


_ESITI_FINALI = frozenset(
    {
        "raccolta completa",
        "raccolta parziale con scarto",
        "scarto totale",
        "interruzione",
    }
)


@dataclass(frozen=True, eq=False)
class Semina:
    """Ciclo produttivo omogeneo realmente avviato."""

    id: SeminaId
    varieta_id: VarietaId
    stato: SeminaState
    quantita_seme: Quantity
    data_avvio: datetime
    cultivar: str
    uso_produttivo: str
    lotto_seme: str
    versione_protocollo: str
    causa_origine: str
    esito_finale: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, SeminaId):
            raise InvariantViolationError("SEMINA richiede un SeminaId valido.")
        if not isinstance(self.varieta_id, VarietaId):
            raise InvariantViolationError("SEMINA richiede un riferimento VarietaId valido.")
        if not isinstance(self.stato, SeminaState):
            raise InvariantViolationError("SEMINA richiede uno stato ufficiale SeminaState.")
        if not isinstance(self.quantita_seme, Quantity):
            raise InvalidQuantityError("SEMINA richiede una quantità di seme valida.")
        if self.quantita_seme.unit is not UnitOfMeasure.GRAM:
            raise InvalidQuantityError("La quantità di seme della SEMINA deve essere espressa in grammi.")
        if self.quantita_seme.value <= 0:
            raise InvalidQuantityError("La quantità di seme della SEMINA deve essere maggiore di zero.")

        object.__setattr__(self, "data_avvio", CurrentSystemDate(self.data_avvio).datetime)

        for nome, valore in (
            ("CULTIVAR", self.cultivar),
            ("USO PRODUTTIVO", self.uso_produttivo),
            ("LOTTO DI SEME", self.lotto_seme),
            ("versione del PROTOCOLLO", self.versione_protocollo),
            ("causa di origine", self.causa_origine),
        ):
            if not isinstance(valore, str) or not valore.strip():
                raise InvariantViolationError(f"SEMINA richiede {nome} non vuoto.")

        if self.stato is SeminaState.CHIUSA:
            if self.esito_finale not in _ESITI_FINALI:
                raise InvariantViolationError(
                    "Una SEMINA CHIUSA richiede un esito finale ufficiale."
                )
        elif self.esito_finale is not None:
            raise InvariantViolationError(
                "L'esito finale può essere registrato esclusivamente per una SEMINA CHIUSA."
            )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Semina):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
