"""Input e output provider-neutral del commit operativo dello Scheduling."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ...domain.time_reference import CurrentSystemDate
from ..committer.context import CommitExecutionContext
from ..committer.models import CommitResult, CommitStatus
from ..run_tracking.models import CompletedSchedulingRun, OpenSchedulingRun
from ..scheduling.models import SchedulingResult


@dataclass(frozen=True)
class ExecuteSchedulingCommitInput:
    """RUN e Scheduling gia prodotti, senza clock o default temporali."""

    open_run: OpenSchedulingRun
    scheduling_result: SchedulingResult
    execution_context: CommitExecutionContext


@dataclass(frozen=True)
class ExecuteSchedulingCommitResult:
    """Esito disponibile soltanto dopo un commit autorevole confermato."""

    scheduling_result: SchedulingResult
    commit_result: CommitResult
    completed_run: CompletedSchedulingRun | None


class OperationalSchedulingStatus(str, Enum):
    """Esiti discriminati del lifecycle operativo della RUN."""

    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class OperationalSchedulingInput:
    """Input operativo: business date e contesto espliciti del caller."""

    current_system_date: CurrentSystemDate
    execution_context: CommitExecutionContext

    def __post_init__(self) -> None:
        if not isinstance(self.current_system_date, CurrentSystemDate):
            raise ValueError("current_system_date deve essere CURRENT_SYSTEM_DATE.")
        if not isinstance(self.execution_context, CommitExecutionContext):
            raise ValueError("execution_context deve essere CommitExecutionContext.")


@dataclass(frozen=True)
class OperationalSchedulingResult:
    """Outcome unico del lifecycle operativo, senza dettagli provider-specific."""

    status: OperationalSchedulingStatus
    execution_context: CommitExecutionContext
    open_run: OpenSchedulingRun
    scheduling_result: SchedulingResult | None = None
    commit_result: CommitResult | None = None
    completed_run: CompletedSchedulingRun | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    primary_error: BaseException | None = field(
        default=None, repr=False, compare=False
    )
    finalization_error: BaseException | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.status, OperationalSchedulingStatus):
            raise ValueError("status deve essere OperationalSchedulingStatus.")
        if not isinstance(self.execution_context, CommitExecutionContext):
            raise ValueError("execution_context deve essere CommitExecutionContext.")
        if not isinstance(self.open_run, OpenSchedulingRun):
            raise ValueError("open_run deve essere OpenSchedulingRun.")
        for name in ("errors", "warnings"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(item, str) or not item for item in values
            ):
                raise ValueError(f"{name} deve contenere stringhe non vuote.")
        for name in ("primary_error", "finalization_error"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, BaseException):
                raise ValueError(f"{name} deve essere una eccezione.")
        if self.status is OperationalSchedulingStatus.COMMITTED:
            if (
                self.commit_result is None
                or self.commit_result.status is not CommitStatus.COMMITTED
                or self.completed_run is None
                or self.errors
                or self.primary_error is not None
                or self.finalization_error is not None
            ):
                raise ValueError("COMMITTED richiede commit e RUN conclusa confermati.")
            return
        if self.status is OperationalSchedulingStatus.RECONCILIATION_REQUIRED:
            if (
                self.commit_result is None
                or self.commit_result.status
                is not CommitStatus.RECONCILIATION_REQUIRED
                or self.completed_run is not None
                or self.primary_error is not None
                or self.finalization_error is not None
            ):
                raise ValueError("RECONCILIATION_REQUIRED richiede outcome incerto.")
            return
        if (
            not self.errors
            or self.commit_result is not None
            or self.primary_error is None
        ):
            raise ValueError("FAILED richiede una failure certa senza commit result.")
