"""Modelli applicativi immutabili del ciclo di una RUN."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.identifiers import RunId
from ...domain.states import RunState
from ...domain.time_reference import CurrentSystemDate
from .errors import InvalidSchedulingRunError


def _version(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidSchedulingRunError("version deve essere un intero non negativo.")


def _counter(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidSchedulingRunError(f"{name} deve essere un intero non negativo.")


def _messages(name: str, value: tuple[str, ...]) -> None:
    if not isinstance(value, tuple) or any(not isinstance(item, str) or not item for item in value):
        raise InvalidSchedulingRunError(f"{name} deve essere una tuple di stringhe non vuote.")


@dataclass(frozen=True)
class OpenSchedulingRun:
    """RUN aperta, distinta dagli stati finali congelati del Domain."""

    run_id: RunId
    started_at: CurrentSystemDate
    simulation: bool
    version: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, RunId):
            raise InvalidSchedulingRunError("run_id deve essere un RunId.")
        if not isinstance(self.started_at, CurrentSystemDate):
            raise InvalidSchedulingRunError("started_at deve essere CURRENT_SYSTEM_DATE.")
        if not isinstance(self.simulation, bool):
            raise InvalidSchedulingRunError("simulation deve essere un booleano.")
        _version(self.version)


@dataclass(frozen=True)
class CompletedSchedulingRun:
    """RUN conclusa con uno degli esiti ufficiali congelati."""

    run_id: RunId
    started_at: CurrentSystemDate
    completed_at: CurrentSystemDate
    simulation: bool
    state: RunState
    programmi_letti: int
    righe_valutate: int
    occorrenze_valutate: int
    ordini_generati: int
    elementi_saltati: int
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    version: int

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, RunId):
            raise InvalidSchedulingRunError("run_id deve essere un RunId.")
        if not isinstance(self.started_at, CurrentSystemDate) or not isinstance(self.completed_at, CurrentSystemDate):
            raise InvalidSchedulingRunError("I riferimenti temporali devono essere CURRENT_SYSTEM_DATE.")
        if self.completed_at.datetime < self.started_at.datetime:
            raise InvalidSchedulingRunError("completed_at non può precedere started_at.")
        if not isinstance(self.simulation, bool) or not isinstance(self.state, RunState):
            raise InvalidSchedulingRunError("simulation o state non validi.")
        for name in (
            "programmi_letti", "righe_valutate", "occorrenze_valutate",
            "ordini_generati", "elementi_saltati",
        ):
            _counter(name, getattr(self, name))
        _messages("warnings", self.warnings)
        _messages("errors", self.errors)
        _version(self.version)
        if self.state is RunState.FAILED and not self.errors:
            raise InvalidSchedulingRunError("Una RUN FAILED richiede almeno un errore.")
        if self.state is RunState.SUCCESS and (self.errors or self.warnings):
            raise InvalidSchedulingRunError("Una RUN SUCCESS non accetta errori o warning.")
        if self.state is RunState.SUCCESS_WITH_WARNINGS and (not self.warnings or self.errors):
            raise InvalidSchedulingRunError("SUCCESS_WITH_WARNINGS richiede warning e non accetta errori.")
