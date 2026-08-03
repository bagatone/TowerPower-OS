"""Servizio applicativo per la sola preparazione del commit."""

from __future__ import annotations

from .errors import InvalidCommitRequestError
from .models import CommitRequest, CommitResult, CommitStatus
from .ports import CommitRepository


class ApplicationCommitter:
    """Prepara un commit senza clock, retry o I/O diretto."""

    def __init__(self, repository: CommitRepository) -> None:
        self._repository = repository

    def prepare(self, request: CommitRequest) -> CommitResult:
        if not isinstance(request, CommitRequest):
            raise InvalidCommitRequestError(
                "request deve essere una CommitRequest valida."
            )
        plan = request.validated_plan
        self._repository.prepare_commit(request)
        return CommitResult(
            run_id=plan.plan.run_id,
            commit_started_at=request.requested_at,
            target_name=plan.target_name,
            expected_operations=plan.plan.expected_logical_row_count,
            status=CommitStatus.PREPARED,
        )
