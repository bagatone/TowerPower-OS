"""Servizio applicativo puro per apertura e chiusura delle RUN."""

from __future__ import annotations

from ...domain.identifiers import RunId
from ...domain.states import RunState
from ...domain.time_reference import CurrentSystemDate
from ..identity.service import PersistentIdAllocator
from ..scheduling.models import SchedulingResult
from .errors import InvalidSchedulingRunError, SchedulingRunConflictError
from .models import CompletedSchedulingRun, OpenSchedulingRun, SchedulingRunCompletion
from .ports import SchedulingRunRepository


class SchedulingRunService:
    """Gestisce il ciclo applicativo di una RUN senza clock o infrastruttura."""

    def __init__(
        self,
        id_allocator: PersistentIdAllocator,
        repository: SchedulingRunRepository,
    ) -> None:
        self._id_allocator = id_allocator
        self._repository = repository

    def open_run(
        self,
        *,
        started_at: CurrentSystemDate,
        simulation: bool,
        run_id: RunId | None = None,
    ) -> OpenSchedulingRun:
        if run_id is None:
            run_id = self._id_allocator.allocate(RunId).identifier
        elif not isinstance(run_id, RunId):
            raise InvalidSchedulingRunError("run_id deve essere un RunId.")
        run = OpenSchedulingRun(run_id=run_id, started_at=started_at, simulation=simulation)
        self._repository.add_open_run(run)
        return run

    def get_run(self, run_id: RunId) -> OpenSchedulingRun | CompletedSchedulingRun:
        """Legge lo stato autorevole corrente senza deduzioni applicative."""
        return self._repository.get(run_id)

    def complete_run(
        self,
        *,
        open_run: OpenSchedulingRun,
        completed_at: CurrentSystemDate,
        scheduling_result: SchedulingResult,
    ) -> CompletedSchedulingRun:
        """Percorso legacy: persiste una conclusione fuori dal commit atomico."""
        proposal = self.propose_completion(
            open_run=open_run,
            completed_at=completed_at,
            scheduling_result=scheduling_result,
        )
        completed = proposal.to_completed_run()
        self._persist(open_run, completed)
        return completed

    def propose_completion(
        self,
        *,
        open_run: OpenSchedulingRun,
        completed_at: CurrentSystemDate,
        scheduling_result: SchedulingResult,
    ) -> SchedulingRunCompletion:
        """Costruisce la conclusione proposta senza persisterla."""
        if not isinstance(open_run, OpenSchedulingRun):
            raise InvalidSchedulingRunError("open_run deve essere una OpenSchedulingRun.")
        if scheduling_result.run_id != open_run.run_id:
            raise InvalidSchedulingRunError("SchedulingResult appartiene a una RUN diversa.")
        if scheduling_result.simulation != open_run.simulation:
            raise InvalidSchedulingRunError("La modalità del risultato non coincide con la RUN.")
        if scheduling_result.esito is RunState.FAILED:
            raise InvalidSchedulingRunError("Un risultato FAILED deve essere registrato tramite fail_run.")
        warnings = scheduling_result.avvisi
        state = RunState.SUCCESS_WITH_WARNINGS if warnings else RunState.SUCCESS
        return SchedulingRunCompletion(
            run_id=open_run.run_id,
            started_at=open_run.started_at,
            completed_at=completed_at,
            simulation=open_run.simulation,
            expected_version=open_run.version,
            final_state=state,
            programmi_letti=scheduling_result.programmi_letti,
            righe_valutate=scheduling_result.righe_valutate,
            occorrenze_valutate=scheduling_result.occorrenze_valutate,
            ordini_generati=scheduling_result.occorrenze_generate,
            elementi_saltati=scheduling_result.occorrenze_saltate_per_idempotenza,
            warnings=warnings,
            errors=(),
        )

    def fail_run(
        self,
        *,
        open_run: OpenSchedulingRun,
        completed_at: CurrentSystemDate,
        errors: tuple[str, ...],
        warnings: tuple[str, ...] = (),
    ) -> CompletedSchedulingRun:
        """Conclude autorevolmente failure operative certe senza ORDINI committati."""
        proposal = self.propose_failure(
            open_run=open_run,
            completed_at=completed_at,
            errors=errors,
            warnings=warnings,
        )
        completed = proposal.to_completed_run()
        self._persist(open_run, completed)
        return completed

    def propose_failure(
        self,
        *,
        open_run: OpenSchedulingRun,
        completed_at: CurrentSystemDate,
        errors: tuple[str, ...],
        warnings: tuple[str, ...] = (),
    ) -> SchedulingRunCompletion:
        """Costruisce una conclusione FAILED proposta senza persisterla."""
        if not isinstance(open_run, OpenSchedulingRun):
            raise InvalidSchedulingRunError("open_run deve essere una OpenSchedulingRun.")
        return SchedulingRunCompletion(
            run_id=open_run.run_id,
            started_at=open_run.started_at,
            completed_at=completed_at,
            simulation=open_run.simulation,
            expected_version=open_run.version,
            final_state=RunState.FAILED,
            programmi_letti=0,
            righe_valutate=0,
            occorrenze_valutate=0,
            ordini_generati=0,
            elementi_saltati=0,
            warnings=warnings,
            errors=errors,
        )

    def _persist(self, open_run: OpenSchedulingRun, completed: CompletedSchedulingRun) -> None:
        if not self._repository.complete(
            run_id=open_run.run_id,
            expected_version=open_run.version,
            completed_run=completed,
        ):
            raise SchedulingRunConflictError(
                f"La RUN {open_run.run_id.value} non è più aperta alla versione attesa."
            )
