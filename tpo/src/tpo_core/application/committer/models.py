"""Modelli immutabili del protocollo applicativo di commit."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain.identifiers import RunId
from ...domain.time_reference import CurrentSystemDate
from ..write_plan.models import ValidatedWritePlan
from .errors import InvalidCommitRequestError


class CommitStatus(str, Enum):
    """Stati disponibili prima di qualsiasi effetto persistente."""

    PREPARED = "PREPARED"


@dataclass(frozen=True)
class CommitRequest:
    """Richiesta applicativa di preparazione di un piano validato."""

    validated_plan: ValidatedWritePlan
    requested_at: CurrentSystemDate

    def __post_init__(self) -> None:
        if not isinstance(self.validated_plan, ValidatedWritePlan):
            raise InvalidCommitRequestError(
                "validated_plan deve essere un ValidatedWritePlan."
            )
        if not isinstance(self.requested_at, CurrentSystemDate):
            raise InvalidCommitRequestError(
                "requested_at deve essere CURRENT_SYSTEM_DATE."
            )
        if (
            self.requested_at.datetime
            < self.validated_plan.validated_at.datetime
        ):
            raise InvalidCommitRequestError(
                "requested_at non può precedere validated_at."
            )


@dataclass(frozen=True)
class CommitResult:
    """Esito della preparazione; le operazioni attese sono righe logiche."""

    run_id: RunId
    commit_started_at: CurrentSystemDate
    target_name: str
    expected_operations: int
    status: CommitStatus

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
        if self.status is not CommitStatus.PREPARED:
            raise InvalidCommitRequestError(
                "L'unico stato disponibile è PREPARED."
            )
