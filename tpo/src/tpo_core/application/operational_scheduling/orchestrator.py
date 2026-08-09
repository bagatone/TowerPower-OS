"""Orchestratore Application del lifecycle completo dello Scheduling operativo."""

from __future__ import annotations

from ...domain.identifiers import RunId
from ...domain.states import RunState
from ..committer.errors import (
    CommitExecutionError,
    CommitPreparationError,
)
from ..committer.models import CommitStatus
from ..identity.service import PersistentIdAllocator
from ..ports.clock import Clock
from ..run_tracking.models import CompletedSchedulingRun, OpenSchedulingRun
from ..run_tracking.errors import RunTrackingError
from ..run_tracking.service import SchedulingRunService
from ..scheduling.use_case import RunScheduling
from ..write_plan.errors import WritePlanError
from .models import (
    ExecuteSchedulingCommitInput,
    OperationalSchedulingInput,
    OperationalSchedulingResult,
    OperationalSchedulingStatus,
)
from .use_case import ExecuteSchedulingCommit, OperationalSchedulingCommitError


_KNOWN_FAILURES = (
    CommitExecutionError,
    CommitPreparationError,
    WritePlanError,
    RunTrackingError,
    OperationalSchedulingCommitError,
)


class OperationalSchedulingOrchestrator:
    """Alloca, apre e porta una RUN fino a un outcome operativo strutturato."""

    def __init__(
        self,
        id_allocator: PersistentIdAllocator,
        run_service: SchedulingRunService,
        run_scheduling: RunScheduling,
        execute_scheduling_commit: ExecuteSchedulingCommit,
        clock: Clock,
    ) -> None:
        self._id_allocator = id_allocator
        self._run_service = run_service
        self._run_scheduling = run_scheduling
        self._execute_scheduling_commit = execute_scheduling_commit
        self._clock = clock

    def execute(self, request: OperationalSchedulingInput) -> OperationalSchedulingResult:
        if not isinstance(request, OperationalSchedulingInput):
            raise ValueError("request deve essere OperationalSchedulingInput.")

        run_id = self._id_allocator.allocate(RunId).identifier
        started_at = self._clock.now()
        open_run = self._run_service.open_run(
            run_id=run_id,
            started_at=started_at,
            simulation=False,
        )
        try:
            scheduling_result = self._run_scheduling.execute(
                run_id=open_run.run_id,
                current_system_date=request.current_system_date,
                simulation=False,
            )
        except Exception as failure:
            return self._finalize_known_failure(
                request,
                open_run,
                failure,
            )

        if scheduling_result.esito is RunState.FAILED:
            failure = OperationalSchedulingCommitError(
                "Scheduling concluso con esito FAILED."
            )
            return self._finalize_known_failure(
                request, open_run, failure,
                scheduling_result=scheduling_result,
                warnings=scheduling_result.avvisi,
            )

        execution_request = ExecuteSchedulingCommitInput(
            open_run=open_run,
            scheduling_result=scheduling_result,
            execution_context=request.execution_context,
        )
        try:
            result = self._execute_scheduling_commit.execute(execution_request)
        except _KNOWN_FAILURES as failure:
            return self._finalize_known_failure(
                request,
                open_run,
                failure,
                scheduling_result=scheduling_result,
                warnings=scheduling_result.avvisi,
            )

        if result.commit_result.status is CommitStatus.RECONCILIATION_REQUIRED:
            return OperationalSchedulingResult(
                status=OperationalSchedulingStatus.RECONCILIATION_REQUIRED,
                execution_context=request.execution_context,
                open_run=open_run,
                scheduling_result=result.scheduling_result,
                commit_result=result.commit_result,
                warnings=result.scheduling_result.avvisi,
            )
        return OperationalSchedulingResult(
            status=OperationalSchedulingStatus.COMMITTED,
            execution_context=request.execution_context,
            open_run=open_run,
            scheduling_result=result.scheduling_result,
            commit_result=result.commit_result,
            completed_run=result.completed_run,
            warnings=result.scheduling_result.avvisi,
        )

    def _finalize_known_failure(
        self,
        request: OperationalSchedulingInput,
        open_run: OpenSchedulingRun,
        failure: BaseException,
        *,
        scheduling_result=None,
        warnings: tuple[str, ...] = (),
    ) -> OperationalSchedulingResult:
        message = str(failure).strip() or type(failure).__name__
        completed_run = None
        finalization_error = None
        try:
            current = self._run_service.get_run(open_run.run_id)
            if isinstance(current, CompletedSchedulingRun):
                return OperationalSchedulingResult(
                    status=OperationalSchedulingStatus.FAILED,
                    execution_context=request.execution_context,
                    open_run=open_run,
                    scheduling_result=scheduling_result,
                    completed_run=current,
                    errors=(message,),
                    warnings=warnings,
                    primary_error=failure,
                )
            if current.version != open_run.version:
                raise OperationalSchedulingCommitError(
                    "La RUN non è più alla versione aperta dall'orchestratore."
                )
            failure_at = self._clock.now()
            completed_run = self._run_service.fail_run(
                open_run=open_run,
                completed_at=failure_at,
                errors=(message,),
                warnings=warnings,
            )
        except Exception as exc:
            finalization_error = exc
        return OperationalSchedulingResult(
            status=OperationalSchedulingStatus.FAILED,
            execution_context=request.execution_context,
            open_run=open_run,
            scheduling_result=scheduling_result,
            completed_run=completed_run,
            errors=(message,),
            warnings=warnings,
            primary_error=failure,
            finalization_error=finalization_error,
        )
