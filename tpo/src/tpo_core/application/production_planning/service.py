"""Orchestrazione applicativa Production Planning, senza algoritmo o writer."""

from __future__ import annotations

from collections.abc import Callable

from .errors import ProductionPlanningError, ProductionPlanningOutcomeUncertain
from .models import (
    InitialProductionPlanningCommand,
    PlanningInputSnapshot,
    ProductionPlanningCommand,
    ProductionPlanningCommit,
    ProductionPlanningResult,
    ProductionPlanningRunOutcome,
    ProductionPlanningRunSnapshot,
    PublicId,
    ReplanProductionPlanningCommand,
    RunMessage,
)
from .ports import (
    IdentityAllocationPort,
    PlanningClockPort,
    ProductionPlanningCommitPort,
    ProductionPlanningInputPort,
    ProductionPlanningRunPort,
)


_CommitBuilder = Callable[
    [ProductionPlanningCommand, PlanningInputSnapshot, ProductionPlanningRunSnapshot],
    ProductionPlanningCommit,
]


class ProductionPlanningService:
    """Coordina le port congelate; il callable di calcolo resta puro e non implementato qui."""

    def __init__(
        self,
        *,
        identity: IdentityAllocationPort,
        inputs: ProductionPlanningInputPort,
        runs: ProductionPlanningRunPort,
        commit: ProductionPlanningCommitPort,
        clock: PlanningClockPort,
        build_commit: _CommitBuilder,
    ) -> None:
        self._identity = identity
        self._inputs = inputs
        self._runs = runs
        self._commit = commit
        self._clock = clock
        self._build_commit = build_commit

    def execute(self, command: ProductionPlanningCommand) -> ProductionPlanningRunOutcome:
        if not isinstance(command, (InitialProductionPlanningCommand, ReplanProductionPlanningCommand)):
            raise ProductionPlanningError(
                "PLANNING_INPUT_INVALID", "INVALID_COMMAND", "Command Production Planning non valido."
            )

        run_id = self._identity.allocate("RUN_PIANIFICAZIONE_PRODUZIONE_ID")
        if not isinstance(run_id, PublicId) or not run_id.value.startswith("RPP-"):
            raise ProductionPlanningError(
                "PLANNING_INPUT_INVALID", "INVALID_RUN_ID", "Identity RUN Planning non valida."
            )
        started_at = self._clock.now()
        run = self._runs.open(
            public_id=run_id,
            policy=command.policy,
            business_at=command.business_at,
            started_at=started_at,
            created_by=command.context.actor.value,
        )

        try:
            snapshot = self._inputs.load(command)
            if snapshot.business_at != command.business_at or snapshot.policy.reference != command.policy:
                raise ProductionPlanningError(
                    "PLANNING_INPUT_INVALID",
                    "SNAPSHOT_SCOPE_MISMATCH",
                    "Snapshot non coerente con business_at e policy richiesti.",
                )
            write_set = self._build_commit(command, snapshot, run)
            if write_set.run != run or write_set.business_at != command.business_at:
                raise ProductionPlanningError(
                    "PLANNING_INPUT_INVALID", "WRITE_SET_SCOPE_MISMATCH", "Write set non coerente con la RUN."
                )
            return self._commit.commit(write_set, completed_at=self._clock.now())
        except ProductionPlanningOutcomeUncertain as error:
            return self._runs.require_reconciliation(
                run=run,
                business_at=command.business_at,
                observed_at=self._clock.now(),
                correlation_id=command.context.correlation_id,
                error=error,
            )
        except ProductionPlanningError as error:
            completed_at = self._clock.now()
            message = RunMessage(
                position=1,
                message_type="ERROR",
                failure_category=error.category,
                code=error.code,
                message=error.safe_message,
                created_at=completed_at,
            )
            self._runs.finalize_failure(
                run=run,
                completed_at=completed_at,
                error=error,
                messages=(message,),
            )
            raise
        except Exception as cause:
            error = ProductionPlanningError(
                "INTERNAL_ERROR",
                "UNEXPECTED_APPLICATION_FAILURE",
                "Failure applicativa inattesa; è richiesta review tecnica.",
            )
            completed_at = self._clock.now()
            self._runs.finalize_failure(
                run=run,
                completed_at=completed_at,
                error=error,
                messages=(
                    RunMessage(
                        position=1,
                        message_type="ERROR",
                        failure_category=error.category,
                        code=error.code,
                        message=error.safe_message,
                        created_at=completed_at,
                    ),
                ),
            )
            raise error from cause
