"""Costruzione pura del Write Plan a partire dallo Scheduling."""

from __future__ import annotations

from ...domain.states import OrdineCreationType, RunState
from ..run_tracking.models import (
    CompletedSchedulingRun,
    OpenSchedulingRun,
    SchedulingRunCompletion,
)
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
        completed_run: CompletedSchedulingRun | None = None,
        open_run: OpenSchedulingRun | None = None,
        completion: SchedulingRunCompletion | None = None,
    ) -> WritePlan:
        if completion is None:
            if not isinstance(completed_run, CompletedSchedulingRun):
                raise InvalidWritePlanError(
                    "È richiesta una SchedulingRunCompletion autorevole."
                )
            completion = _legacy_completion(completed_run)
        if open_run is not None:
            _validate_open_run(open_run, completion)
        self._validate_result(scheduling_result, completion)
        records = scheduling_result.ordini_generati
        if not records:
            raise InvalidWritePlanError(
                "Il risultato non contiene record da includere nel Write Plan."
            )
        _validate_provenance(records)
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
            run_id=completion.run_id,
            created_at=completion.completed_at,
            records=records,
            expected_record_count=len(records),
            expected_logical_row_count=logical_rows,
            idempotency_keys=keys,
            warnings=completion.warnings,
            completion=completion,
        )

    @staticmethod
    def _validate_result(
        result: SchedulingResult,
        completion: SchedulingRunCompletion,
    ) -> None:
        if result.run_id != completion.run_id:
            raise WritePlanRunMismatchError(
                "SchedulingResult e CompletedSchedulingRun appartengono a RUN diverse."
            )
        if result.simulation != completion.simulation:
            raise WritePlanRunMismatchError(
                "La modalità dello SchedulingResult non coincide con la RUN."
            )
        if completion.final_state is RunState.FAILED:
            raise InvalidWritePlanError("Una RUN FAILED non può produrre un Write Plan.")
        if result.esito is RunState.FAILED:
            raise InvalidWritePlanError(
                "Uno SchedulingResult FAILED non può produrre un Write Plan."
            )
        if result.simulation:
            raise InvalidWritePlanError(
                "Una RUN in simulazione non può produrre un Write Plan per il commit."
            )
        if result.esito is not completion.final_state:
            raise WritePlanConsistencyError(
                "L'esito della RUN non coincide con lo SchedulingResult."
            )
        if result.avvisi != completion.warnings:
            raise WritePlanConsistencyError(
                "I warning della RUN non coincidono con lo SchedulingResult."
            )
        counters = (
            (completion.programmi_letti, result.programmi_letti),
            (completion.righe_valutate, result.righe_valutate),
            (completion.occorrenze_valutate, result.occorrenze_valutate),
            (completion.ordini_generati, result.occorrenze_generate),
            (
                completion.elementi_saltati,
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


def _legacy_completion(run: CompletedSchedulingRun) -> SchedulingRunCompletion:
    if run.version <= 0:
        raise InvalidWritePlanError("La RUN conclusa legacy non possiede una versione valida.")
    return SchedulingRunCompletion(
        run_id=run.run_id,
        started_at=run.started_at,
        completed_at=run.completed_at,
        simulation=run.simulation,
        expected_version=run.version - 1,
        final_state=run.state,
        programmi_letti=run.programmi_letti,
        righe_valutate=run.righe_valutate,
        occorrenze_valutate=run.occorrenze_valutate,
        ordini_generati=run.ordini_generati,
        elementi_saltati=run.elementi_saltati,
        warnings=run.warnings,
        errors=run.errors,
    )


def _validate_open_run(
    open_run: OpenSchedulingRun,
    completion: SchedulingRunCompletion,
) -> None:
    if not isinstance(open_run, OpenSchedulingRun):
        raise InvalidWritePlanError("open_run non valida.")
    if (
        open_run.run_id != completion.run_id
        or open_run.started_at != completion.started_at
        or open_run.simulation != completion.simulation
        or open_run.version != completion.expected_version
    ):
        raise WritePlanConsistencyError(
            "OpenSchedulingRun e proposta di completamento non sono coerenti."
        )


def _validate_provenance(records) -> None:
    """Richiede provenance autorevole e completa per ogni riga automatica."""
    for record in records:
        if record.ordine.tipo_creazione is not OrdineCreationType.AUTOMATICO:
            raise InvalidWritePlanError(
                "Il Write Plan accetta esclusivamente ORDINI AUTOMATICI."
            )
        if record.ordine.programma_fornitura_id is None:
            raise InvalidWritePlanError(
                "Un ORDINE AUTOMATICO richiede PROGRAMMA_FORNITURA."
            )
        if not isinstance(record.chiave_idempotenza, str) or not record.chiave_idempotenza.strip():
            raise InvalidWritePlanError(
                "Un ORDINE AUTOMATICO richiede una chiave idempotente."
            )
        expected_positions = set(range(1, len(record.ordine.righe) + 1))
        actual_positions = {item.order_line_position for item in record.provenance}
        if actual_positions != expected_positions:
            raise InvalidWritePlanError(
                "Ogni riga ORDINE automatica deve possedere almeno una provenance."
            )
        if any(
            item.programma_fornitura_id != record.ordine.programma_fornitura_id
            for item in record.provenance
        ):
            raise InvalidWritePlanError(
                "La provenance appartiene a un PROGRAMMA_FORNITURA diverso."
            )
        identities = tuple(
            (
                item.programma_fornitura_id,
                item.programma_version,
                item.programma_line_position,
                item.order_line_position,
            )
            for item in record.provenance
        )
        if len(set(identities)) != len(identities):
            raise InvalidWritePlanError("La provenance contiene origini duplicate.")
        if identities != tuple(sorted(identities, key=lambda item: (item[3], item[2]))):
            raise InvalidWritePlanError("La provenance non possiede un ordine stabile.")
