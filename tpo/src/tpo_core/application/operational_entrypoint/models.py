"""Contratto pubblico provider-neutral dell'entry point operativo."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.identifiers import RunId
from ...domain.time_reference import CurrentSystemDate
from ..operational_scheduling.models import (
    OperationalSchedulingResult,
    OperationalSchedulingStatus,
)
from ..run_tracking.models import CompletedSchedulingRun


@dataclass(frozen=True)
class RecognizedOperationalIdentity:
    """Identità del canale già riconosciuta, distinta da ActorId."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("operational_identity deve essere una stringa non vuota.")
        if self.value != self.value.strip():
            raise ValueError(
                "operational_identity non accetta whitespace iniziale o finale."
            )


@dataclass(frozen=True)
class OperationalSchedulingIntent:
    """Intenzione esterna priva dei dettagli del protocollo di commit."""

    business_date: CurrentSystemDate
    operational_identity: RecognizedOperationalIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.business_date, CurrentSystemDate):
            raise ValueError("business_date deve essere CURRENT_SYSTEM_DATE.")
        if not isinstance(
            self.operational_identity, RecognizedOperationalIdentity
        ):
            raise ValueError(
                "operational_identity deve essere RecognizedOperationalIdentity."
            )


@dataclass(frozen=True)
class OperationalReconciliationContext:
    """Proiezione provider-neutral dell'esito incerto per il caller."""

    run_id: RunId
    requested_at: CurrentSystemDate
    idempotency_keys: tuple[str, ...]
    expected_record_count: int
    expected_logical_row_count: int
    correlation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, RunId):
            raise ValueError("run_id deve essere RunId.")
        if not isinstance(self.requested_at, CurrentSystemDate):
            raise ValueError("requested_at deve essere CURRENT_SYSTEM_DATE.")
        if not isinstance(self.idempotency_keys, tuple) or any(
            not isinstance(key, str) or not key.strip()
            for key in self.idempotency_keys
        ):
            raise ValueError(
                "idempotency_keys deve contenere stringhe non vuote."
            )
        if len(set(self.idempotency_keys)) != len(self.idempotency_keys):
            raise ValueError("idempotency_keys contiene duplicati.")
        for name in ("expected_record_count", "expected_logical_row_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} deve essere un intero non negativo.")
        if (
            not isinstance(self.correlation_id, str)
            or not self.correlation_id.strip()
            or self.correlation_id != self.correlation_id.strip()
        ):
            raise ValueError(
                "correlation_id deve essere una stringa non vuota senza whitespace esterno."
            )


@dataclass(frozen=True)
class OperationalEntryPointResult:
    """Outcome pubblico senza CommitExecutionContext o dipendenze runtime."""

    status: OperationalSchedulingStatus
    run_id: RunId
    completed_run: CompletedSchedulingRun | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    reconciliation_context: OperationalReconciliationContext | None

    @classmethod
    def from_operational_result(
        cls, result: OperationalSchedulingResult
    ) -> OperationalEntryPointResult:
        source_context = (
            result.commit_result.reconciliation_context
            if result.commit_result is not None
            else None
        )
        reconciliation_context = (
            OperationalReconciliationContext(
                run_id=source_context.run_id,
                requested_at=source_context.requested_at,
                idempotency_keys=source_context.idempotency_keys,
                expected_record_count=source_context.expected_record_count,
                expected_logical_row_count=source_context.expected_logical_row_count,
                correlation_id=source_context.correlation_id,
            )
            if source_context is not None
            else None
        )
        return cls(
            status=result.status,
            run_id=result.open_run.run_id,
            completed_run=result.completed_run,
            errors=result.errors,
            warnings=result.warnings,
            reconciliation_context=reconciliation_context,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.status, OperationalSchedulingStatus):
            raise ValueError("status deve essere OperationalSchedulingStatus.")
        if not isinstance(self.run_id, RunId):
            raise ValueError("run_id deve essere RunId.")
        if self.status is OperationalSchedulingStatus.COMMITTED:
            if self.completed_run is None or self.reconciliation_context is not None:
                raise ValueError("COMMITTED richiede una RUN conclusa confermata.")
        elif self.status is OperationalSchedulingStatus.RECONCILIATION_REQUIRED:
            if self.completed_run is not None or self.reconciliation_context is None:
                raise ValueError(
                    "RECONCILIATION_REQUIRED richiede il relativo contesto."
                )
        elif self.reconciliation_context is not None:
            raise ValueError("FAILED non può contenere contesto di riconciliazione.")
