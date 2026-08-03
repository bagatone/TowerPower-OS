"""Modello applicativo immutabile e serializzabile del Write Plan."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ...domain.identifiers import RunId
from ...domain.time_reference import CurrentSystemDate
from ..scheduling.models import ScheduledOrderRecord
from .errors import DuplicateIdempotencyKeyError, InvalidWritePlanError


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

    @staticmethod
    def _validate_count(name: str, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise InvalidWritePlanError(f"{name} deve essere un intero positivo.")

    def to_dict(self) -> dict[str, Any]:
        """Crea un'anteprima semantica stabile composta da soli tipi JSON."""
        return {
            "created_at": self.created_at.datetime.isoformat(),
            "expected_logical_row_count": self.expected_logical_row_count,
            "expected_record_count": self.expected_record_count,
            "idempotency_keys": list(self.idempotency_keys),
            "records": [self._record_dict(record) for record in self.records],
            "run_id": self.run_id.value,
            "warnings": list(self.warnings),
        }

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
