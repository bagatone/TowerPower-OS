"""Validazione applicativa pre-commit di un Write Plan."""

from __future__ import annotations

from ...domain.time_reference import CurrentSystemDate
from .errors import (
    DuplicateWritePlanKeyError,
    DuplicateWritePlanRecordError,
    ExistingIdempotencyKeyError,
    InvalidWritePlanError,
    InvalidWriteTargetSnapshotError,
    WritePlanCountMismatchError,
    WritePlanValidationError,
    WriteSchemaMismatchError,
    WriteTargetMismatchError,
)
from .models import (
    ValidatedWritePlan,
    WritePlan,
    WritePlanValidationSnapshot,
    WriteTargetSnapshot,
)
from .ports import WritePlanValidationRepository


WRITE_TARGET_ORDINI = "ORDINI"
WRITE_SCHEMA_ORDINI = "ORDINI"
WRITE_SCHEMA_VERSION = "1.0"


class WritePlanValidator:
    """Convalida integralmente un piano senza scritture o retry."""

    def __init__(self, repository: WritePlanValidationRepository) -> None:
        self._repository = repository

    def validate(
        self,
        *,
        plan: WritePlan,
        validated_at: CurrentSystemDate,
        expected_target_name: str,
        expected_schema_name: str,
        expected_schema_version: str,
    ) -> ValidatedWritePlan:
        self._validate_arguments(
            plan,
            validated_at,
            expected_target_name,
            expected_schema_name,
            expected_schema_version,
        )
        self._validate_plan(plan)
        snapshot = self._repository.get_target_snapshot(
            target_name=expected_target_name
        )
        if not isinstance(snapshot, WriteTargetSnapshot):
            raise InvalidWriteTargetSnapshotError(
                "Il repository non ha restituito un WriteTargetSnapshot."
            )
        if snapshot.target_name != expected_target_name:
            raise WriteTargetMismatchError(
                "Il target disponibile non coincide con quello atteso."
            )
        if snapshot.schema_name != expected_schema_name:
            raise WriteSchemaMismatchError(
                "Il nome dello schema disponibile non coincide con quello atteso."
            )
        if snapshot.schema_version != expected_schema_version:
            raise WriteSchemaMismatchError(
                "La versione dello schema disponibile non coincide con quella attesa."
            )
        existing = set(snapshot.existing_idempotency_keys)
        already_present = tuple(key for key in plan.idempotency_keys if key in existing)
        if already_present:
            raise ExistingIdempotencyKeyError(
                "Il target contiene già almeno una chiave idempotente del piano."
            )
        proof = WritePlanValidationSnapshot(
            run_id=plan.run_id,
            expected_record_count=plan.expected_record_count,
            expected_logical_row_count=plan.expected_logical_row_count,
            checked_existing_key_count=len(snapshot.existing_idempotency_keys),
            schema_name=snapshot.schema_name,
            schema_version=snapshot.schema_version,
            target_name=snapshot.target_name,
        )
        return ValidatedWritePlan(
            plan=plan,
            validated_at=validated_at,
            existing_idempotency_keys_checked=snapshot.existing_idempotency_keys,
            target_name=snapshot.target_name,
            expected_schema_name=snapshot.schema_name,
            expected_schema_version=snapshot.schema_version,
            validation_snapshot=proof,
            warnings=plan.warnings,
        )

    @staticmethod
    def _validate_arguments(
        plan: WritePlan,
        validated_at: CurrentSystemDate,
        target: str,
        schema: str,
        version: str,
    ) -> None:
        if not isinstance(plan, WritePlan):
            raise WritePlanValidationError("plan deve essere un WritePlan.")
        if not isinstance(validated_at, CurrentSystemDate):
            raise WritePlanValidationError(
                "validated_at deve essere CURRENT_SYSTEM_DATE."
            )
        for name, value in (
            ("expected_target_name", target),
            ("expected_schema_name", schema),
            ("expected_schema_version", version),
        ):
            if not isinstance(value, str) or not value.strip():
                raise WritePlanValidationError(
                    f"{name} deve essere una stringa non vuota."
                )

    @staticmethod
    def _validate_plan(plan: WritePlan) -> None:
        records = plan.records
        if not isinstance(records, tuple) or not records:
            raise InvalidWritePlanError("Il Write Plan non può essere vuoto.")
        _validate_provenance(records)
        completion = plan.completion
        if completion is not None:
            if completion.run_id != plan.run_id:
                raise InvalidWritePlanError("La proposta appartiene a una RUN diversa.")
            if completion.completed_at != plan.created_at:
                raise InvalidWritePlanError("completed_at non coincide con il piano.")
            if completion.ordini_generati != len(records):
                raise WritePlanCountMismatchError(
                    "ordini_generati non coincide con i record del piano."
                )
            if completion.simulation:
                raise InvalidWritePlanError(
                    "Una RUN in simulazione non può produrre un commit autorevole."
                )
        if plan.expected_record_count != len(records):
            raise WritePlanCountMismatchError(
                "expected_record_count non coincide con i record."
            )
        logical_rows = sum(len(record.ordine.righe) for record in records)
        if plan.expected_logical_row_count != logical_rows:
            raise WritePlanCountMismatchError(
                "expected_logical_row_count non coincide con le righe logiche."
            )
        record_keys = tuple(record.chiave_idempotenza for record in records)
        if any(not isinstance(key, str) or not key.strip() for key in record_keys):
            raise InvalidWritePlanError(
                "Il piano contiene una chiave idempotente vuota."
            )
        if len(set(record_keys)) != len(record_keys):
            raise DuplicateWritePlanKeyError(
                "Il piano contiene chiavi idempotenti duplicate."
            )
        if plan.idempotency_keys != record_keys:
            raise InvalidWritePlanError(
                "Le chiavi dichiarate non coincidono con quelle dei record."
            )
        order_ids = tuple(record.ordine.id for record in records)
        if len(set(order_ids)) != len(order_ids):
            raise DuplicateWritePlanRecordError(
                "Il piano contiene più record per lo stesso ordine logico."
            )


def _validate_provenance(records) -> None:
    for record in records:
        positions = tuple(item.order_line_position for item in record.provenance)
        expected = set(range(1, len(record.ordine.righe) + 1))
        if set(positions) != expected:
            raise InvalidWritePlanError("Il piano contiene provenance orfana o incompleta.")
        if any(position > len(record.ordine.righe) for position in positions):
            raise InvalidWritePlanError("La provenance punta a una riga ORDINE inesistente.")
        if any(
            item.programma_fornitura_id != record.ordine.programma_fornitura_id
            for item in record.provenance
        ):
            raise InvalidWritePlanError("La provenance non coincide con il PROGRAMMA dell'ORDINE.")
        keys = tuple(
            (item.programma_version, item.programma_line_position, item.order_line_position)
            for item in record.provenance
        )
        if len(set(keys)) != len(keys):
            raise InvalidWritePlanError("La provenance contiene associazioni duplicate.")
