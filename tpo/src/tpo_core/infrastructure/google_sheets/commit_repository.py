"""Adapter di commit atomico e riconciliazione per il foglio ORDINI."""

from __future__ import annotations

from collections import Counter
from typing import Protocol

from ...application.committer.errors import (
    CommitExecutionError,
    CommitExistingKeyError,
    CommitPreparationError,
    CommitSchemaChangedError,
    CommitSerializationError,
    InvalidCommitRequestError,
)
from ...application.committer.models import CommitExecutionReceipt, CommitRequest
from ...application.ports.clock import Clock
from .errors import GoogleSheetsRepositoryError
from .mappers import (
    ORDINI_HEADERS,
    ORDINI_SHEET_NAME,
    scheduled_orders_from_rows,
    scheduled_orders_to_rows,
)


class _CommitGateway(Protocol):
    def read_headers(
        self, *, spreadsheet_id: str, sheet_name: str
    ) -> tuple[str, ...]: ...

    def read_rows(
        self, *, spreadsheet_id: str, sheet_name: str
    ) -> tuple[dict[str, str], ...]: ...

    def append_rows(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
        rows: tuple[dict[str, str], ...],
    ) -> None: ...


class GoogleSheetsCommitRepository:
    """Esegue un solo append e verifica il risultato tramite rilettura."""

    def __init__(
        self,
        gateway: _CommitGateway,
        spreadsheet_id: str,
        clock: Clock,
        sheet_name: str = ORDINI_SHEET_NAME,
    ) -> None:
        if not isinstance(spreadsheet_id, str) or not spreadsheet_id.strip():
            raise CommitPreparationError(
                "spreadsheet_id deve essere una stringa non vuota."
            )
        if not isinstance(sheet_name, str) or not sheet_name.strip():
            raise CommitPreparationError(
                "sheet_name deve essere una stringa non vuota."
            )
        self._gateway = gateway
        self._spreadsheet_id = spreadsheet_id
        self._clock = clock
        self._sheet_name = sheet_name

    def prepare_commit(self, request: CommitRequest) -> None:
        """Verifica soltanto il target logico, senza accedere a Google Sheets."""
        self._validate_request_target(request, CommitPreparationError)

    def execute_commit(self, request: CommitRequest) -> CommitExecutionReceipt:
        """Controlla, appende una volta e riconcilia senza retry."""
        self._validate_request_target(request, CommitExecutionError)
        plan = request.validated_plan.plan
        self._verify_headers()
        existing_records = self._read_records("lettura pre-commit")
        existing_keys = {
            record.chiave_idempotenza for record in existing_records
        }
        collisions = tuple(
            key for key in plan.idempotency_keys if key in existing_keys
        )
        if collisions:
            raise CommitExistingKeyError(
                "Una o più chiavi idempotenti del piano sono già presenti nel target."
            )

        try:
            rows = scheduled_orders_to_rows(plan.records)
        except (TypeError, ValueError) as exc:
            raise CommitSerializationError(
                "Impossibile serializzare i record del piano validato."
            ) from exc
        self._validate_serialized_rows(request, rows)

        try:
            self._gateway.append_rows(
                spreadsheet_id=self._spreadsheet_id,
                sheet_name=self._sheet_name,
                rows=rows,
            )
        except GoogleSheetsRepositoryError as exc:
            raise CommitExecutionError(
                "Append Google Sheets non completato con esito certo."
            ) from exc

        post_records = self._read_records("riconciliazione post-append")
        key_counts = Counter(
            record.chiave_idempotenza for record in post_records
        )
        reconciled = tuple(
            key for key in plan.idempotency_keys if key_counts[key] == 1
        )
        reconciliation_complete = reconciled == plan.idempotency_keys
        completed_at = self._clock.now()
        if completed_at.datetime < request.requested_at.datetime:
            raise CommitExecutionError(
                "Il Clock ha prodotto commit_completed_at precedente a requested_at."
            )
        return CommitExecutionReceipt(
            run_id=plan.run_id,
            target_name=request.validated_plan.target_name,
            expected_record_count=plan.expected_record_count,
            expected_logical_row_count=plan.expected_logical_row_count,
            appended_physical_row_count=len(rows),
            reconciled_idempotency_keys=reconciled,
            commit_completed_at=completed_at,
            reconciliation_complete=reconciliation_complete,
        )

    def _validate_request_target(
        self,
        request: CommitRequest,
        error_type: type[CommitPreparationError] | type[CommitExecutionError],
    ) -> None:
        if not isinstance(request, CommitRequest):
            raise InvalidCommitRequestError(
                "request deve essere una CommitRequest valida."
            )
        validated = request.validated_plan
        if validated.target_name != ORDINI_SHEET_NAME:
            raise error_type("Il piano validato non è destinato a ORDINI.")
        if self._sheet_name != ORDINI_SHEET_NAME:
            raise error_type("Il repository di commit può operare soltanto su ORDINI.")

    def _verify_headers(self) -> None:
        try:
            headers = self._gateway.read_headers(
                spreadsheet_id=self._spreadsheet_id,
                sheet_name=self._sheet_name,
            )
        except GoogleSheetsRepositoryError as exc:
            raise CommitSchemaChangedError(
                "Impossibile verificare lo schema fisico del target."
            ) from exc
        if headers != ORDINI_HEADERS:
            raise CommitSchemaChangedError(
                "Le intestazioni fisiche di ORDINI non coincidono con lo schema congelato."
            )

    def _read_records(self, phase: str):
        try:
            rows = self._gateway.read_rows(
                spreadsheet_id=self._spreadsheet_id,
                sheet_name=self._sheet_name,
            )
            return scheduled_orders_from_rows(rows)
        except GoogleSheetsRepositoryError as exc:
            raise CommitExecutionError(
                f"Impossibile completare la {phase}."
            ) from exc

    @staticmethod
    def _validate_serialized_rows(
        request: CommitRequest,
        rows: tuple[dict[str, str], ...],
    ) -> None:
        plan = request.validated_plan.plan
        if len(rows) != plan.expected_logical_row_count:
            raise CommitSerializationError(
                "Il numero di righe fisiche non coincide con le righe logiche attese."
            )
        if any(tuple(row.keys()) != ORDINI_HEADERS for row in rows):
            raise CommitSerializationError(
                "Le righe serializzate non rispettano lo schema fisico congelato."
            )
        if any(any(not isinstance(value, str) for value in row.values()) for row in rows):
            raise CommitSerializationError(
                "Le righe serializzate contengono valori fisici non testuali."
            )
