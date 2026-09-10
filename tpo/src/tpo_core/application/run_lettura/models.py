"""Contratti immutabili della query RUN/RUN_LOG (sola lettura) V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md
(Fase 1, boundary runs/run_log -- la vista del log di esecuzione dello
scheduler delle 06:00, docs/architecture/AUTOMATED_OPERATIONAL_SCHEDULING_FREEZE.md).
Query a sola lettura.

RUN_LOG e' potenzialmente voluminoso (un evento per ogni passo interno del
run) mentre RUN e' un riepilogo per esecuzione: per questo l'elenco RUN e'
sempre completo (nessun filtro), ma RUN_LOG si legge un run alla volta
(RichiediRunLog), non come elenco globale.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from ...domain.identifiers import RunId
from .errors import InvalidRunLetturaQueryError

STATI_RUN_AMMESSI = frozenset({"SUCCESS", "SUCCESS_WITH_WARNINGS", "FAILED"})
TIPI_RUN_MESSAGGIO_AMMESSI = frozenset({"WARNING", "ERROR"})
LIVELLI_RUN_LOG_AMMESSI = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


@dataclass(frozen=True)
class RichiediElencoRun:
    """Nessun filtro in V1: elenco completo, ordinato per started_at decrescente."""


@dataclass(frozen=True)
class RichiediRunLog:
    run_id: RunId

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, RunId):
            raise InvalidRunLetturaQueryError("run_id non valido.")


@dataclass(frozen=True)
class RunMessaggio:
    tipo: str
    posizione: int
    messaggio: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.tipo not in TIPI_RUN_MESSAGGIO_AMMESSI:
            raise InvalidRunLetturaQueryError("tipo non valido.")
        if self.posizione <= 0:
            raise InvalidRunLetturaQueryError("posizione deve essere positiva.")
        if not self.messaggio or not self.messaggio.strip():
            raise InvalidRunLetturaQueryError("messaggio non puo' essere vuoto.")


@dataclass(frozen=True)
class Run:
    run_id: RunId
    started_at: datetime
    completed_at: datetime | None
    simulation: bool
    state: str | None
    programmi_letti: int
    righe_valutate: int
    occorrenze_valutate: int
    ordini_generati: int
    elementi_saltati: int
    messaggi: tuple[RunMessaggio, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, RunId):
            raise InvalidRunLetturaQueryError("run_id non valido.")
        if (self.completed_at is None) != (self.state is None):
            raise InvalidRunLetturaQueryError(
                "state deve essere presente se e solo se completed_at lo e'."
            )
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise InvalidRunLetturaQueryError("completed_at non puo' precedere started_at.")
        if self.state is not None and self.state not in STATI_RUN_AMMESSI:
            raise InvalidRunLetturaQueryError("state non valido.")
        for nome, valore in (
            ("programmi_letti", self.programmi_letti),
            ("righe_valutate", self.righe_valutate),
            ("occorrenze_valutate", self.occorrenze_valutate),
            ("ordini_generati", self.ordini_generati),
            ("elementi_saltati", self.elementi_saltati),
        ):
            if valore < 0:
                raise InvalidRunLetturaQueryError(f"{nome} non puo' essere negativo.")
        if not isinstance(self.messaggi, tuple) or any(
            not isinstance(m, RunMessaggio) for m in self.messaggi
        ):
            raise InvalidRunLetturaQueryError("messaggi deve essere una tupla di RunMessaggio.")


@dataclass(frozen=True)
class ElencoRun:
    runs: tuple[Run, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.runs, tuple) or any(not isinstance(r, Run) for r in self.runs):
            raise InvalidRunLetturaQueryError("runs deve essere una tupla di Run.")


@dataclass(frozen=True)
class RunLogVoce:
    occurred_at: datetime
    level: str
    event_type: str
    message: str
    context: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.level not in LIVELLI_RUN_LOG_AMMESSI:
            raise InvalidRunLetturaQueryError("level non valido.")
        if not self.event_type or not self.event_type.strip():
            raise InvalidRunLetturaQueryError("event_type non puo' essere vuoto.")
        if not self.message or not self.message.strip():
            raise InvalidRunLetturaQueryError("message non puo' essere vuoto.")
        if not isinstance(self.context, Mapping):
            raise InvalidRunLetturaQueryError("context deve essere una mappa.")


@dataclass(frozen=True)
class RunLog:
    run_id: RunId
    voci: tuple[RunLogVoce, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, RunId):
            raise InvalidRunLetturaQueryError("run_id non valido.")
        if not isinstance(self.voci, tuple) or any(
            not isinstance(v, RunLogVoce) for v in self.voci
        ):
            raise InvalidRunLetturaQueryError("voci deve essere una tupla di RunLogVoce.")
