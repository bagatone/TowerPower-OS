"""Caso d'uso autorevole per Scheduling, validazione e commit atomico."""

from __future__ import annotations

from ...domain.states import RunState
from ..committer.models import CommitRequest, CommitStatus
from ..committer.service import ApplicationCommitter
from ..run_tracking.service import SchedulingRunService
from ..scheduling.use_case import RunScheduling
from ..write_plan.service import WritePlanBuilder
from ..write_plan.validation import (
    WRITE_SCHEMA_ORDINI,
    WRITE_SCHEMA_VERSION,
    WRITE_TARGET_ORDINI,
    WritePlanValidator,
)
from .models import ExecuteSchedulingCommitInput, ExecuteSchedulingCommitResult


class OperationalSchedulingCommitError(RuntimeError):
    """Il percorso operativo non può produrre un risultato autorevole."""


class ExecuteSchedulingCommit:
    """Compone i servizi Application senza conoscere il provider persistente."""

    def __init__(
        self,
        run_scheduling: RunScheduling,
        run_service: SchedulingRunService,
        write_plan_builder: WritePlanBuilder,
        write_plan_validator: WritePlanValidator,
        committer: ApplicationCommitter,
    ) -> None:
        self._run_scheduling = run_scheduling
        self._run_service = run_service
        self._write_plan_builder = write_plan_builder
        self._write_plan_validator = write_plan_validator
        self._committer = committer

    def execute(
        self, request: ExecuteSchedulingCommitInput
    ) -> ExecuteSchedulingCommitResult:
        if not isinstance(request, ExecuteSchedulingCommitInput):
            raise OperationalSchedulingCommitError(
                "request deve essere un ExecuteSchedulingCommitInput."
            )
        if request.open_run.simulation:
            raise OperationalSchedulingCommitError(
                "Il commit operativo non accetta RUN in simulazione."
            )

        scheduling_result = self._run_scheduling.execute(
            run_id=request.open_run.run_id,
            current_system_date=request.current_system_date,
            simulation=False,
        )
        if scheduling_result.esito is RunState.FAILED:
            raise OperationalSchedulingCommitError(
                "Uno SchedulingResult FAILED non può essere committato."
            )
        completion = self._run_service.propose_completion(
            open_run=request.open_run,
            completed_at=request.completion_at,
            scheduling_result=scheduling_result,
        )
        plan = self._write_plan_builder.build(
            scheduling_result=scheduling_result,
            open_run=request.open_run,
            completion=completion,
        )
        validated_plan = self._write_plan_validator.validate(
            plan=plan,
            validated_at=request.completion_at,
            expected_target_name=WRITE_TARGET_ORDINI,
            expected_schema_name=WRITE_SCHEMA_ORDINI,
            expected_schema_version=WRITE_SCHEMA_VERSION,
        )
        commit_request = CommitRequest(
            validated_plan=validated_plan,
            requested_at=request.requested_at,
            execution_context=request.execution_context,
        )
        commit_result = self._committer.commit(
            commit_request,
            request.commit_completed_at,
        )
        if commit_result.status is not CommitStatus.COMMITTED:
            raise OperationalSchedulingCommitError(
                "Il commit non ha prodotto una conferma autorevole completa."
            )
        completed_run = completion.to_completed_run()
        return ExecuteSchedulingCommitResult(
            scheduling_result=scheduling_result,
            commit_result=commit_result,
            completed_run=completed_run,
        )
