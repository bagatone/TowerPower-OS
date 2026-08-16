"""Orchestrazione applicativa Production Planning V1."""

from __future__ import annotations

from .assembler import ProductionPlanningCommitAssembler
from .errors import (
    ProductionPlanningError,
    ProductionPlanningOutcomeUncertain,
    ProductionPlanningRunFinalizationOutcomeUncertain,
)
from .models import (
    InitialProductionPlanningCommand,
    ProductionPlanningAssemblyInput,
    ProductionPlanningCommand,
    ProductionPlanningIdentityBundle,
    ProductionPlanningRunOutcome,
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


class ProductionPlanningService:
    def __init__(self, *, identity: IdentityAllocationPort,
                 inputs: ProductionPlanningInputPort,
                 runs: ProductionPlanningRunPort,
                 commit: ProductionPlanningCommitPort,
                 clock: PlanningClockPort, engine, assembler: ProductionPlanningCommitAssembler) -> None:
        self._identity = identity
        self._inputs = inputs
        self._runs = runs
        self._commit = commit
        self._clock = clock
        self._engine = engine
        self._assembler = assembler

    def execute(self, command: ProductionPlanningCommand) -> ProductionPlanningRunOutcome:
        if not isinstance(command, (InitialProductionPlanningCommand, ReplanProductionPlanningCommand)):
            raise ProductionPlanningError("PLANNING_INPUT_INVALID", "INVALID_COMMAND", "Command Production Planning non valido.")
        run_id = self._identity.allocate("RUN_PIANIFICAZIONE_PRODUZIONE_ID")
        if not isinstance(run_id, PublicId) or not run_id.value.startswith("RPP-"):
            raise ProductionPlanningError("PLANNING_INPUT_INVALID", "INVALID_RUN_ID", "Identity RUN Planning non valida.")
        run = self._runs.open(
            public_id=run_id, policy=command.policy, business_at=command.business_at,
            started_at=self._clock.now(), created_by=command.context.actor.value,
        )
        try:
            loaded = self._inputs.load(command)
            snapshot = loaded.snapshot
            if isinstance(command, InitialProductionPlanningCommand) and loaded.allocation_disposition_decisions:
                raise ProductionPlanningError(
                    "PLANNING_INPUT_INVALID", "INITIAL_DISPOSITIONS_NOT_EMPTY",
                    "Initial planning non ammette disposition di allocazioni esistenti.",
                )
            if snapshot.business_at != command.business_at or snapshot.policy.reference != command.policy:
                raise ProductionPlanningError("PLANNING_INPUT_INVALID", "SNAPSHOT_SCOPE_MISMATCH", "Snapshot non coerente con business_at e policy richiesti.")
            candidates = tuple(self._engine.calculate(snapshot))
            plan = self._assembler.plan(ProductionPlanningAssemblyInput(
                command, run, snapshot, candidates,
                loaded.allocation_disposition_decisions,
            ))
            assignments = tuple(
                (slot, self._identity.allocate(slot.sequence_name))
                for slot in plan.identity_slots
            )
            bundle = ProductionPlanningIdentityBundle.from_slot_assignments(assignments)
            write_set = self._assembler.materialize(plan, bundle)
            return self._commit.commit(write_set, completed_at=self._clock.now())
        except ProductionPlanningOutcomeUncertain as error:
            try:
                return self._runs.require_reconciliation(
                    run=run, business_at=command.business_at,
                    observed_at=self._clock.now(), correlation_id=command.context.correlation_id,
                    error=error,
                )
            except Exception as cause:
                raise ProductionPlanningRunFinalizationOutcomeUncertain(
                    attempted_operation="REQUIRE_RECONCILIATION", original_error=error,
                    planning_run_public_id=run.public_id,
                    correlation_id=command.context.correlation_id,
                ) from cause
        except ProductionPlanningRunFinalizationOutcomeUncertain:
            raise
        except Exception as cause:
            error = cause if isinstance(cause, ProductionPlanningError) else ProductionPlanningError(
                "INTERNAL_ERROR", "UNEXPECTED_APPLICATION_FAILURE",
                "Failure applicativa inattesa; è richiesta review tecnica.",
            )
            completed_at = self._clock.now()
            try:
                self._runs.finalize_failure(
                    run=run, completed_at=completed_at, error=error,
                    messages=(RunMessage(
                        position=1, message_type="ERROR", code=error.code,
                        message=error.safe_message, created_at=completed_at,
                        failure_category=error.category,
                    ),),
                )
            except Exception as finalization_cause:
                raise ProductionPlanningRunFinalizationOutcomeUncertain(
                    attempted_operation="FINALIZE_FAILURE", original_error=error,
                    planning_run_public_id=run.public_id,
                    correlation_id=command.context.correlation_id,
                ) from finalization_cause
            if error is cause:
                raise
            raise error from cause
