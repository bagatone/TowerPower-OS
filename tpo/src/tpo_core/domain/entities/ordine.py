"""Entità e Value Object del dominio ORDINI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from ..errors import InvalidQuantityError, InvariantViolationError
from ..identifiers import ClienteId, OrdineId, ProgrammaFornituraId, VarietaId
from ..quantities import Quantity
from ..states import OrdineState


@dataclass(frozen=True)
class RigaOrdine:
    """Riga prodotto immutabile di un ORDINE."""

    varieta_id: VarietaId
    quantita: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvariantViolationError("La riga ORDINE richiede un VarietaId valido.")
        if not isinstance(self.quantita, Quantity):
            raise InvalidQuantityError("La riga ORDINE richiede una quantità valida.")
        if self.quantita.value <= 0:
            raise InvalidQuantityError("La quantità della riga ORDINE deve essere maggiore di zero.")


@dataclass(frozen=True)
class PrenotazioneOrdine:
    """Riserva logica derivata da una riga ORDINE."""

    varieta_id: VarietaId
    quantita: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvariantViolationError("La PRENOTAZIONE richiede un VarietaId valido.")
        if not isinstance(self.quantita, Quantity):
            raise InvalidQuantityError("La PRENOTAZIONE richiede una quantità valida.")
        if self.quantita.value <= 0:
            raise InvalidQuantityError("La quantità PRENOTATA deve essere maggiore di zero.")


@dataclass(frozen=True, eq=False)
class Ordine:
    """Richiesta storica di prodotto appartenente a un CLIENTE."""

    id: OrdineId
    cliente_id: ClienteId
    data_ordine: date
    righe: tuple[RigaOrdine, ...]
    stato: OrdineState
    programma_fornitura_id: ProgrammaFornituraId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, OrdineId):
            raise InvariantViolationError("ORDINE richiede un OrdineId valido.")
        if not isinstance(self.cliente_id, ClienteId):
            raise InvariantViolationError("ORDINE richiede un riferimento ClienteId valido.")
        if not isinstance(self.data_ordine, date) or isinstance(self.data_ordine, datetime):
            raise InvariantViolationError("ORDINE richiede una data_ordine valida.")
        if not isinstance(self.righe, tuple) or not self.righe:
            raise InvariantViolationError("ORDINE richiede almeno una riga in una tuple.")
        if any(not isinstance(riga, RigaOrdine) for riga in self.righe):
            raise InvariantViolationError("ORDINE accetta esclusivamente righe valide.")
        if not isinstance(self.stato, OrdineState):
            raise InvariantViolationError("ORDINE richiede uno stato ufficiale OrdineState.")
        if self.programma_fornitura_id is not None and not isinstance(
            self.programma_fornitura_id, ProgrammaFornituraId
        ):
            raise InvariantViolationError(
                "L'origine automatica richiede un ProgrammaFornituraId valido."
            )

    @property
    def prenotazioni(self) -> tuple[PrenotazioneOrdine, ...]:
        """Deriva una riserva logica immutabile per ciascuna riga."""

        return tuple(
            PrenotazioneOrdine(riga.varieta_id, riga.quantita)
            for riga in self.righe
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Ordine):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
