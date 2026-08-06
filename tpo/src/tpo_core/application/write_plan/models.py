"""Modello applicativo immutabile e serializzabile del Write Plan."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ...domain.identifiers import RunId
from ...domain.time_reference import CurrentSystemDate
from ..run_tracking.models import SchedulingRunCompletion
from ..scheduling.models import ScheduledOrderRecord
from .errors import (
    DuplicateIdempotencyKeyError,
    InvalidWritePlanError,
    InvalidWriteTargetSnapshotError,
    WritePlanValidationError,
)


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _messages(name: str, value: tuple[str, ...]) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise InvalidWritePlanError(
            f"{name} deve essere una tuple di stringhe non vuote."
        )


@dataclass(frozen=True)
class WritePlan:
    """Transazione applicativa proposta da una RUN conclusa."""

    run_id: RunId
    created_at: CurrentSystemDate
    records: tuple[ScheduledOrderRecord, ...]
    expected_record_count: int
    expected_logical_row_count: int
    idempotency_keys: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    completion: SchedulingRunCompletion | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, RunId):
            raise InvalidWritePlanError("run_id deve essere un RunId.")
        if not isinstance(self.created_at, CurrentSystemDate):
            raise InvalidWritePlanError("created_at deve essere CURRENT_SYSTEM_DATE.")
        if not isinstance(self.records, tuple) or not self.records:
            raise InvalidWritePlanError("records deve contenere almeno un record.")
        if any(not isinstance(record, ScheduledOrderRecord) for record in self.records):
            raise InvalidWritePlanError("records contiene elementi non validi.")
        self._validate_count("expected_record_count", self.expected_record_count)
        self._validate_count(
            "expected_logical_row_count", self.expected_logical_row_count
        )
        if self.expected_record_count != len(self.records):
            raise InvalidWritePlanError("expected_record_count non coincide con i record.")
        logical_rows = sum(len(record.ordine.righe) for record in self.records)
        if self.expected_logical_row_count != logical_rows:
            raise InvalidWritePlanError(
                "expected_logical_row_count non coincide con le righe logiche."
            )
        if not isinstance(self.idempotency_keys, tuple):
            raise InvalidWritePlanError("idempotency_keys deve essere una tuple.")
        if any(
            not isinstance(key, str) or not key.strip()
            for key in self.idempotency_keys
        ):
            raise InvalidWritePlanError("Le chiavi idempotenti devono essere stringhe non vuote.")
        if len(set(self.idempotency_keys)) != len(self.idempotency_keys):
            raise DuplicateIdempotencyKeyError(
                "Il Write Plan contiene chiavi idempotenti duplicate."
            )
        expected_keys = tuple(record.chiave_idempotenza for record in self.records)
        if self.idempotency_keys != expected_keys:
            raise InvalidWritePlanError(
                "idempotency_keys non coincide con le chiavi dei record."
            )
        _messages("warnings", self.warnings)
        if self.completion is not None:
            if not isinstance(self.completion, SchedulingRunCompletion):
                raise InvalidWritePlanError("completion non valida.")
            if self.completion.run_id != self.run_id:
                raise InvalidWritePlanError("completion appartiene a una RUN diversa.")
            if self.completion.completed_at != self.created_at:
                raise InvalidWritePlanError("created_at non coincide con completed_at.")
            if self.completion.warnings != self.warnings:
                raise InvalidWritePlanError("I warning non coincidono con completion.")

    @staticmethod
    def _validate_count(name: str, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise InvalidWritePlanError(f"{name} deve essere un intero positivo.")

    def to_dict(self) -> dict[str, Any]:
        """Crea un'anteprima semantica stabile composta da soli tipi JSON."""
        payload = {
            "created_at": self.created_at.datetime.isoformat(),
            "expected_logical_row_count": self.expected_logical_row_count,
            "expected_record_count": self.expected_record_count,
            "idempotency_keys": list(self.idempotency_keys),
            "records": [self._record_dict(record) for record in self.records],
            "run_id": self.run_id.value,
            "warnings": list(self.warnings),
        }
        if self.completion is not None:
            payload["completion"] = {
                "completed_at": self.completion.completed_at.datetime.isoformat(),
                "elementi_saltati": self.completion.elementi_saltati,
                "errors": list(self.completion.errors),
                "expected_version": self.completion.expected_version,
                "final_state": self.completion.final_state.value,
                "occorrenze_valutate": self.completion.occorrenze_valutate,
                "ordini_generati": self.completion.ordini_generati,
                "programmi_letti": self.completion.programmi_letti,
                "righe_valutate": self.completion.righe_valutate,
                "run_id": self.completion.run_id.value,
                "simulation": self.completion.simulation,
                "started_at": self.completion.started_at.datetime.isoformat(),
                "warnings": list(self.completion.warnings),
            }
        return payload

    @staticmethod
    def _record_dict(record: ScheduledOrderRecord) -> dict[str, Any]:
        ordine = record.ordine
        return {
            "chiave_idempotenza": record.chiave_idempotenza,
            "cliente_id": ordine.cliente_id.value,
            "data_consegna_prevista": record.data_consegna_prevista.isoformat(),
            "data_ordine": ordine.data_ordine.isoformat(),
            "ordine_id": ordine.id.value,
            "programma_fornitura_id": (
                ordine.programma_fornitura_id.value
                if ordine.programma_fornitura_id is not None
                else None
            ),
            "tipo_creazione": ordine.tipo_creazione.value,
            "provenance": [
                {
                    "order_line_position": item.order_line_position,
                    "programma_fornitura_id": item.programma_fornitura_id.value,
                    "programma_line_position": item.programma_line_position,
                    "programma_version": item.programma_version,
                }
                for item in record.provenance
            ],
            "righe": [
                {
                    "quantita": _decimal_text(riga.quantita.value),
                    "unita": riga.quantita.unit.value,
                    "varieta_id": riga.varieta_id.value,
                }
                for riga in ordine.righe
            ],
        }

    def to_json(self) -> str:
        """Serializza deterministicamente il piano senza I/O."""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )


def _non_empty_text(name: str, value: str, error_type: type[ValueError]) -> None:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{name} deve essere una stringa non vuota.")


def _non_negative_count(name: str, value: int, error_type: type[ValueError]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise error_type(f"{name} deve essere un intero non negativo.")


@dataclass(frozen=True)
class WriteTargetSnapshot:
    """Vista applicativa minima del target disponibile alla validazione."""

    target_name: str
    schema_name: str
    schema_version: str
    existing_idempotency_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        error = InvalidWriteTargetSnapshotError
        _non_empty_text("target_name", self.target_name, error)
        _non_empty_text("schema_name", self.schema_name, error)
        _non_empty_text("schema_version", self.schema_version, error)
        if not isinstance(self.existing_idempotency_keys, tuple):
            raise error("existing_idempotency_keys deve essere una tuple.")
        if any(
            not isinstance(key, str) or not key.strip()
            for key in self.existing_idempotency_keys
        ):
            raise error("Le chiavi esistenti devono essere stringhe non vuote.")
        if len(set(self.existing_idempotency_keys)) != len(
            self.existing_idempotency_keys
        ):
            raise error("Lo snapshot contiene chiavi esistenti duplicate.")


@dataclass(frozen=True)
class WritePlanValidationSnapshot:
    """Prove strutturate prodotte dalla validazione applicativa."""

    run_id: RunId
    expected_record_count: int
    expected_logical_row_count: int
    checked_existing_key_count: int
    schema_name: str
    schema_version: str
    target_name: str

    def __post_init__(self) -> None:
        error = WritePlanValidationError
        if not isinstance(self.run_id, RunId):
            raise error("run_id dello snapshot deve essere un RunId.")
        for name in ("expected_record_count", "expected_logical_row_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise error(f"{name} deve essere un intero positivo.")
        _non_negative_count(
            "checked_existing_key_count", self.checked_existing_key_count, error
        )
        _non_empty_text("schema_name", self.schema_name, error)
        _non_empty_text("schema_version", self.schema_version, error)
        _non_empty_text("target_name", self.target_name, error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_existing_key_count": self.checked_existing_key_count,
            "expected_logical_row_count": self.expected_logical_row_count,
            "expected_record_count": self.expected_record_count,
            "run_id": self.run_id.value,
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "target_name": self.target_name,
        }


@dataclass(frozen=True)
class ValidatedWritePlan:
    """Write Plan che ha superato una validazione pre-commit completa."""

    plan: WritePlan
    validated_at: CurrentSystemDate
    existing_idempotency_keys_checked: tuple[str, ...]
    target_name: str
    expected_schema_name: str
    expected_schema_version: str
    validation_snapshot: WritePlanValidationSnapshot
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        error = WritePlanValidationError
        if not isinstance(self.plan, WritePlan):
            raise error("plan deve essere un WritePlan.")
        if not isinstance(self.validated_at, CurrentSystemDate):
            raise error("validated_at deve essere CURRENT_SYSTEM_DATE.")
        _non_empty_text("target_name", self.target_name, error)
        _non_empty_text("expected_schema_name", self.expected_schema_name, error)
        _non_empty_text("expected_schema_version", self.expected_schema_version, error)
        if not isinstance(self.existing_idempotency_keys_checked, tuple):
            raise error("existing_idempotency_keys_checked deve essere una tuple.")
        if any(
            not isinstance(key, str) or not key.strip()
            for key in self.existing_idempotency_keys_checked
        ):
            raise error("Le chiavi verificate devono essere stringhe non vuote.")
        if len(set(self.existing_idempotency_keys_checked)) != len(
            self.existing_idempotency_keys_checked
        ):
            raise error("Le chiavi verificate non possono essere duplicate.")
        if not isinstance(self.validation_snapshot, WritePlanValidationSnapshot):
            raise error("validation_snapshot non valido.")
        snapshot = self.validation_snapshot
        if (
            snapshot.run_id != self.plan.run_id
            or snapshot.expected_record_count != self.plan.expected_record_count
            or snapshot.expected_logical_row_count
            != self.plan.expected_logical_row_count
            or snapshot.checked_existing_key_count
            != len(self.existing_idempotency_keys_checked)
            or snapshot.target_name != self.target_name
            or snapshot.schema_name != self.expected_schema_name
            or snapshot.schema_version != self.expected_schema_version
        ):
            raise error("Le prove di validazione non coincidono con il piano.")
        _messages("warnings", self.warnings)
        if self.warnings != self.plan.warnings:
            raise error("I warning validati non coincidono con il piano.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "existing_key_count_checked": len(
                self.existing_idempotency_keys_checked
            ),
            "idempotency_keys": list(self.plan.idempotency_keys),
            "logical_row_count": self.plan.expected_logical_row_count,
            "plan": self.plan.to_dict(),
            "record_count": self.plan.expected_record_count,
            "run_id": self.plan.run_id.value,
            "schema_name": self.expected_schema_name,
            "schema_version": self.expected_schema_version,
            "target_name": self.target_name,
            "validated_at": self.validated_at.datetime.isoformat(),
            "validation_snapshot": self.validation_snapshot.to_dict(),
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
