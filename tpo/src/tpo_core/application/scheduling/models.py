"""Modelli immutabili di input e output dello Scheduling Engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...domain.entities.ordine import Ordine, RigaOrdine
from ...domain.entities.programma_fornitura import ProgrammaFornitura
from ...domain.errors import InvariantViolationError
from ...domain.identifiers import ClienteId, IdGenerator, ProgrammaFornituraId, RunId
from ...domain.states import RunState
from ...domain.time_reference import CurrentSystemDate
from .provenance import OrderLineProvenance, VersionedProgrammaFornitura


@dataclass(frozen=True)
class GeneratedOrderDraft:
    """Anteprima applicativa di un ORDINE dovuto, priva di OrdineId."""

    cliente_id: ClienteId
    programma_fornitura_id: ProgrammaFornituraId
    data_ordine: date
    data_consegna_prevista: date
    righe: tuple[RigaOrdine, ...]
    chiave_idempotenza: str
    provenance: tuple[OrderLineProvenance, ...] = ()


@dataclass(frozen=True)
class ScheduledOrderRecord:
    """ORDINE generato corredato dai metadati applicativi di scheduling."""

    ordine: Ordine
    data_consegna_prevista: date
    chiave_idempotenza: str
    provenance: tuple[OrderLineProvenance, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, tuple) or any(
            not isinstance(item, OrderLineProvenance) for item in self.provenance
        ):
            raise InvariantViolationError(
                "provenance deve essere una tuple di OrderLineProvenance."
            )


@dataclass(frozen=True)
class SchedulingRequest:
    """Input completo e immutabile di una singola esecuzione."""

    run_id: RunId
    current_system_date: CurrentSystemDate
    programmi: tuple[VersionedProgrammaFornitura | ProgrammaFornitura, ...]
    ordini_esistenti: tuple[ScheduledOrderRecord, ...] = ()
    id_generator: IdGenerator | None = None
    simulation: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, RunId):
            raise InvariantViolationError("SchedulingRequest richiede un RunId valido.")
        if not isinstance(self.current_system_date, CurrentSystemDate):
            raise InvariantViolationError("SchedulingRequest richiede CURRENT_SYSTEM_DATE.")
        if not isinstance(self.programmi, tuple):
            raise InvariantViolationError(
                "Lo Scheduling autorevole richiede PROGRAMMI_FORNITURA versionati."
            )
        if any(not isinstance(item, VersionedProgrammaFornitura) for item in self.programmi):
            legacy_valid = self.simulation and all(
                isinstance(item, ProgrammaFornitura) for item in self.programmi
            )
            if not legacy_valid:
                raise InvariantViolationError(
                    "Lo Scheduling autorevole richiede PROGRAMMI_FORNITURA versionati."
                )
        if not isinstance(self.ordini_esistenti, tuple) or any(
            not isinstance(record, ScheduledOrderRecord) for record in self.ordini_esistenti
        ):
            raise InvariantViolationError("Gli ORDINI esistenti devono essere record validi.")
        if not isinstance(self.simulation, bool):
            raise InvariantViolationError("simulation deve essere un booleano.")
        if not self.simulation and self.id_generator is None:
            raise InvariantViolationError("L'esecuzione operativa richiede un IdGenerator.")


@dataclass(frozen=True)
class SchedulingResult:
    """Descrizione immutabile del risultato, senza effetti persistenti."""

    run_id: RunId
    ordini_generati: tuple[ScheduledOrderRecord, ...]
    anteprime: tuple[GeneratedOrderDraft, ...]
    programmi_letti: int
    righe_valutate: int
    occorrenze_valutate: int
    occorrenze_generate: int
    occorrenze_saltate_per_idempotenza: int
    avvisi: tuple[str, ...]
    simulation: bool
    esito: RunState
