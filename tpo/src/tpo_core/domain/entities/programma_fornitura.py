"""Entità e Value Object del PROGRAMMA_FORNITURA."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any

from ..errors import InvalidQuantityError, InvariantViolationError
from ..identifiers import ClienteId, ProgrammaFornituraId, VarietaId
from ..quantities import Quantity
from ..states import ProgrammaFornituraState


class TipoRicorrenza(str, Enum):
    """Configurazioni temporali approvate per una riga di fornitura."""

    SETTIMANALE = "SETTIMANALE"
    QUINDICINALE = "QUINDICINALE"
    MENSILE = "MENSILE"
    OGNI_X_GIORNI = "OGNI_X_GIORNI"
    GIORNI_SETTIMANA = "GIORNI_SETTIMANA"


@dataclass(frozen=True)
class ConfigurazioneTemporale:
    """Configurazione temporale immutabile di una riga."""

    tipo: TipoRicorrenza
    intervallo_giorni: int | None = None
    giorni_settimana: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.tipo, TipoRicorrenza):
            raise InvariantViolationError("La ricorrenza richiede un TipoRicorrenza ufficiale.")

        if self.tipo is TipoRicorrenza.OGNI_X_GIORNI:
            if (
                not isinstance(self.intervallo_giorni, int)
                or isinstance(self.intervallo_giorni, bool)
                or self.intervallo_giorni <= 0
            ):
                raise InvariantViolationError(
                    "OGNI_X_GIORNI richiede un intervallo intero positivo."
                )
        elif self.intervallo_giorni is not None:
            raise InvariantViolationError(
                "L'intervallo in giorni è ammesso esclusivamente per OGNI_X_GIORNI."
            )

        if not isinstance(self.giorni_settimana, tuple):
            raise InvariantViolationError("I giorni della settimana devono essere una tuple.")
        if self.tipo is TipoRicorrenza.GIORNI_SETTIMANA:
            if not self.giorni_settimana:
                raise InvariantViolationError(
                    "GIORNI_SETTIMANA richiede almeno un giorno ISO."
                )
            if any(
                not isinstance(giorno, int)
                or isinstance(giorno, bool)
                or not 1 <= giorno <= 7
                for giorno in self.giorni_settimana
            ):
                raise InvariantViolationError("I giorni ISO devono essere compresi tra 1 e 7.")
            if len(set(self.giorni_settimana)) != len(self.giorni_settimana):
                raise InvariantViolationError("I giorni della settimana non possono essere duplicati.")
        elif self.giorni_settimana:
            raise InvariantViolationError(
                "I giorni specifici sono ammessi esclusivamente per GIORNI_SETTIMANA."
            )


@dataclass(frozen=True)
class RigaProgrammaFornitura:
    """Riga prodotto immutabile del PROGRAMMA_FORNITURA."""

    varieta_id: VarietaId
    quantita: Quantity
    configurazione_temporale: ConfigurazioneTemporale

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvariantViolationError("La riga richiede un riferimento VarietaId valido.")
        if not isinstance(self.quantita, Quantity):
            raise InvalidQuantityError("La riga richiede una quantità valida.")
        if self.quantita.value <= 0:
            raise InvalidQuantityError("La quantità della riga deve essere maggiore di zero.")
        if not isinstance(self.configurazione_temporale, ConfigurazioneTemporale):
            raise InvariantViolationError(
                "La riga richiede una ConfigurazioneTemporale valida."
            )


@dataclass(frozen=True, eq=False)
class ProgrammaFornitura:
    """Accordo operativo continuativo con un CLIENTE."""

    id: ProgrammaFornituraId
    cliente_id: ClienteId
    righe: tuple[RigaProgrammaFornitura, ...]
    data_inizio: date
    stato: ProgrammaFornituraState
    finestra_operativa_giorni: int
    data_fine: date | None = None
    orario_generazione: time = time(5, 0)

    def __post_init__(self) -> None:
        if not isinstance(self.id, ProgrammaFornituraId):
            raise InvariantViolationError(
                "PROGRAMMA_FORNITURA richiede un ProgrammaFornituraId valido."
            )
        if not isinstance(self.cliente_id, ClienteId):
            raise InvariantViolationError(
                "PROGRAMMA_FORNITURA richiede un riferimento ClienteId valido."
            )
        if not isinstance(self.righe, tuple) or not self.righe:
            raise InvariantViolationError(
                "PROGRAMMA_FORNITURA richiede almeno una riga in una tuple."
            )
        if any(not isinstance(riga, RigaProgrammaFornitura) for riga in self.righe):
            raise InvariantViolationError(
                "PROGRAMMA_FORNITURA accetta esclusivamente righe valide."
            )
        if not isinstance(self.data_inizio, date) or isinstance(self.data_inizio, datetime):
            raise InvariantViolationError("PROGRAMMA_FORNITURA richiede una data_inizio valida.")
        if self.data_fine is not None:
            if not isinstance(self.data_fine, date) or isinstance(self.data_fine, datetime):
                raise InvariantViolationError("data_fine deve essere una date valida.")
            if self.data_fine < self.data_inizio:
                raise InvariantViolationError("data_fine non può precedere data_inizio.")
        if not isinstance(self.stato, ProgrammaFornituraState):
            raise InvariantViolationError(
                "PROGRAMMA_FORNITURA richiede uno stato ufficiale."
            )
        if not isinstance(self.orario_generazione, time):
            raise InvariantViolationError("L'orario di generazione deve essere un time.")
        if (
            not isinstance(self.finestra_operativa_giorni, int)
            or isinstance(self.finestra_operativa_giorni, bool)
            or self.finestra_operativa_giorni < 0
        ):
            raise InvariantViolationError(
                "La finestra operativa deve essere un intero non negativo."
            )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, ProgrammaFornitura):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
