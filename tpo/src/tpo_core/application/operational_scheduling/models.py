"""Input e output provider-neutral del commit operativo dello Scheduling."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.time_reference import CurrentSystemDate
from ..committer.context import CommitExecutionContext
from ..committer.models import CommitResult
from ..run_tracking.models import CompletedSchedulingRun, OpenSchedulingRun
from ..scheduling.models import SchedulingResult


@dataclass(frozen=True)
class ExecuteSchedulingCommitInput:
    """Riferimenti espliciti necessari, senza clock o default temporali."""

    open_run: OpenSchedulingRun
    current_system_date: CurrentSystemDate
    execution_context: CommitExecutionContext


@dataclass(frozen=True)
class ExecuteSchedulingCommitResult:
    """Esito disponibile soltanto dopo un commit autorevole confermato."""

    scheduling_result: SchedulingResult
    commit_result: CommitResult
    completed_run: CompletedSchedulingRun | None
