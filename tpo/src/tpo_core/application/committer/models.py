"""Modelli immutabili del protocollo applicativo di commit."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain.identifiers import ActorId, RunId
from ...domain.time_reference import CurrentSystemDate
from ..write_plan.models import ValidatedWritePlan
from ..run_tracking.models import SchedulingRunCompletion
from .errors import InvalidCommitRequestError
from .context import CommitExecutionContext


class CommitStatus(str, Enum):
    """Stati del protocollo applicativo di commit."""

    PREPARED = "PREPARED"
    COMMITTED = "COMMITTED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class CommitRequest:
    """Richiesta applicativa di preparazione di un piano validato."""

    validated_plan: ValidatedWritePlan
    requested_at: CurrentSystemDate
    execution_context: CommitExecutionContext

    def __post_init__(self) -> None:
        if not isinstance(self.validated_plan, ValidatedWritePlan):
            raise InvalidCommitRequestError(
                "validated_plan deve essere un ValidatedWritePlan."
            )
        if not isinstance(self.requested_at, CurrentSystemDate):
            raise InvalidCommitRequestError(
                "requested_at deve essere CURRENT_SYSTEM_DATE."
            )
        if not isinstance(self.execution_context, CommitExecutionContext):
            raise InvalidCommitRequestError(
                "execution_context deve essere un CommitExecutionContext."
            )
        if (
            self.requested_at.datetime
            < self.validated_plan.validated_at.datetime
        ):
            raise InvalidCommitRequestError(
                "requested_at non può precedere validated_at."
            )

    @property
    def completion(self) -> SchedulingRunCompletion | None:
        """Contesto atomico della RUN; ``None`` identifica il percorso legacy."""
        return self.validated_plan.plan.completion

    @property
    def expected_version(self) -> int | None:
        return self.completion.expected_version if self.completion is not None else None

    @property
    def actor(self) -> ActorId:
        return self.execution_context.actor

    @property
    def audit_reason(self) -> str:
        return self.execution_context.reason

    @property
    def correlation_id(self) -> str:
        return self.execution_context.correlation_id


@dataclass(frozen=True)
class CommitResult:
    """Esito; ``committed_operations`` conta le righe operative persistite."""

    run_id: RunId
    commit_started_at: CurrentSystemDate
    target_name: str
    expected_operations: int
    status: CommitStatus
    committed_operations: int | None = None
    reconciled_idempotency_keys: tuple[str, ...] = ()
    commit_completed_at: CurrentSystemDate | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, RunId):
            raise InvalidCommitRequestError("run_id deve essere un RunId.")
        if not isinstance(self.commit_started_at, CurrentSystemDate):
            raise InvalidCommitRequestError(
                "commit_started_at deve essere CURRENT_SYSTEM_DATE."
            )
        if not isinstance(self.target_name, str) or not self.target_name.strip():
            raise InvalidCommitRequestError(
                "target_name deve essere una stringa non vuota."
            )
        if (
            isinstance(self.expected_operations, bool)
            or not isinstance(self.expected_operations, int)
            or self.expected_operations <= 0
        ):
            raise InvalidCommitRequestError(
                "expected_operations deve essere un intero positivo."
            )
        if not isinstance(self.status, CommitStatus):
            raise InvalidCommitRequestError(
                "status deve essere un CommitStatus."
            )
        if not isinstance(self.reconciled_idempotency_keys, tuple) or any(
            not isinstance(key, str) or not key.strip()
            for key in self.reconciled_idempotency_keys
        ):
            raise InvalidCommitRequestError(
                "reconciled_idempotency_keys deve essere una tuple di stringhe non vuote."
            )
        if len(set(self.reconciled_idempotency_keys)) != len(
            self.reconciled_idempotency_keys
        ):
            raise InvalidCommitRequestError(
                "reconciled_idempotency_keys contiene duplicati."
            )
        if self.status is CommitStatus.PREPARED:
            if (
                self.committed_operations is not None
                or self.reconciled_idempotency_keys
                or self.commit_completed_at is not None
            ):
                raise InvalidCommitRequestError(
                    "PREPARED non può contenere dati di commit completato."
                )
            return
        if (
            isinstance(self.committed_operations, bool)
            or not isinstance(self.committed_operations, int)
            or self.committed_operations < 0
        ):
            raise InvalidCommitRequestError(
                "committed_operations deve essere un intero non negativo."
            )
        if not isinstance(self.commit_completed_at, CurrentSystemDate):
            raise InvalidCommitRequestError(
                "commit_completed_at deve essere CURRENT_SYSTEM_DATE."
            )
        if self.commit_completed_at.datetime < self.commit_started_at.datetime:
            raise InvalidCommitRequestError(
                "commit_completed_at non può precedere commit_started_at."
            )


@dataclass(frozen=True)
class CommitExecutionReceipt:
    """Prova immutabile dei conteggi e della successiva riconciliazione.

    I record attesi sono testate ORDINE, le righe logiche sono RIGHE_ORDINE del
    piano e le righe fisiche appendate sono righe operative ORDINE persistite.
    """

    run_id: RunId
    target_name: str
    expected_record_count: int
    expected_logical_row_count: int
    appended_physical_row_count: int
    reconciled_idempotency_keys: tuple[str, ...]
    commit_completed_at: CurrentSystemDate
    reconciliation_complete: bool

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, RunId):
            raise InvalidCommitRequestError("run_id deve essere un RunId.")
        if not isinstance(self.target_name, str) or not self.target_name.strip():
            raise InvalidCommitRequestError(
                "target_name deve essere una stringa non vuota."
            )
        for name in (
            "expected_record_count",
            "expected_logical_row_count",
            "appended_physical_row_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise InvalidCommitRequestError(
                    f"{name} deve essere un intero non negativo."
                )
        if not isinstance(self.reconciled_idempotency_keys, tuple) or any(
            not isinstance(key, str) or not key.strip()
            for key in self.reconciled_idempotency_keys
        ):
            raise InvalidCommitRequestError(
                "reconciled_idempotency_keys deve essere una tuple di stringhe non vuote."
            )
        if len(set(self.reconciled_idempotency_keys)) != len(
            self.reconciled_idempotency_keys
        ):
            raise InvalidCommitRequestError(
                "reconciled_idempotency_keys contiene duplicati."
            )
        if not isinstance(self.commit_completed_at, CurrentSystemDate):
            raise InvalidCommitRequestError(
                "commit_completed_at deve essere CURRENT_SYSTEM_DATE."
            )
        if not isinstance(self.reconciliation_complete, bool):
            raise InvalidCommitRequestError(
                "reconciliation_complete deve essere booleano."
            )
