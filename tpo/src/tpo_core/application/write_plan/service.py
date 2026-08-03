"""Costruzione pura del Write Plan a partire dallo Scheduling."""

from __future__ import annotations

from ...domain.states import RunState
from ..run_tracking.models import CompletedSchedulingRun
from ..scheduling.models import SchedulingResult
from .errors import (
    DuplicateIdempotencyKeyError,
    InvalidWritePlanError,
    WritePlanConsistencyError,
    WritePlanRunMismatchError,
)
from .models import WritePlan


class WritePlanBuilder:
    """Conserva il risultato applicativo senza proiettarlo su una persistenza."""

    def build(
        self,
        *,
        scheduling_result: SchedulingResult,
        completed_run: CompletedSchedulingRun,
    ) -> WritePlan:
        self._validate_result(scheduling_result, completed_run)
        records = scheduling_result.ordini_generati
        if not records:
            raise InvalidWritePlanError(
                "Il risultato non contiene record da includere nel Write Plan."
            )
        keys = tuple(record.chiave_idempotenza for record in records)
        if any(not isinstance(key, str) or not key.strip() for key in keys):
            raise InvalidWritePlanError(
                "Ogni record deve possedere una chiave idempotente non vuota."
            )
        if len(set(keys)) != len(keys):
            raise DuplicateIdempotencyKeyError(
                "Il risultato contiene chiavi idempotenti duplicate."
            )
        logical_rows = sum(len(record.ordine.righe) for record in records)
        return WritePlan(
            run_id=completed_run.run_id,
            created_at=completed_run.completed_at,
            records=records,
            expected_record_count=len(records),
            expected_logical_row_count=logical_rows,
            idempotency_keys=keys,
            warnings=completed_run.warnings,
        )

    @staticmethod
    def _validate_result(
        result: SchedulingResult,
        completed_run: CompletedSchedulingRun,
    ) -> None:
        if result.run_id != completed_run.run_id:
            raise WritePlanRunMismatchError(
                "SchedulingResult e CompletedSchedulingRun appartengono a RUN diverse."
            )
        if result.simulation != completed_run.simulation:
            raise WritePlanRunMismatchError(
                "La modalità dello SchedulingResult non coincide con la RUN."
            )
        if completed_run.state is RunState.FAILED:
            raise InvalidWritePlanError("Una RUN FAILED non può produrre un Write Plan.")
        if result.esito is RunState.FAILED:
            raise InvalidWritePlanError(
                "Uno SchedulingResult FAILED non può produrre un Write Plan."
            )
        if result.simulation:
            raise InvalidWritePlanError(
                "Una RUN in simulazione non può produrre un Write Plan per il commit."
            )
        if result.esito is not completed_run.state:
            raise WritePlanConsistencyError(
                "L'esito della RUN non coincide con lo SchedulingResult."
            )
        if result.avvisi != completed_run.warnings:
            raise WritePlanConsistencyError(
                "I warning della RUN non coincidono con lo SchedulingResult."
            )
        counters = (
            (completed_run.programmi_letti, result.programmi_letti),
            (completed_run.righe_valutate, result.righe_valutate),
            (completed_run.occorrenze_valutate, result.occorrenze_valutate),
            (completed_run.ordini_generati, result.occorrenze_generate),
            (
                completed_run.elementi_saltati,
                result.occorrenze_saltate_per_idempotenza,
            ),
        )
        if any(run_value != result_value for run_value, result_value in counters):
            raise WritePlanConsistencyError(
                "I contatori della RUN non coincidono con lo SchedulingResult."
            )
        if result.occorrenze_generate != len(result.ordini_generati):
            raise WritePlanConsistencyError(
                "Il numero di record non coincide con le occorrenze generate."
            )
