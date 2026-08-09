"""Servizio applicativo per la sola preparazione del commit."""

from __future__ import annotations

from .errors import CommitReceiptMismatchError, InvalidCommitRequestError
from .models import (
    CommitExecutionReceipt,
    CommitOutcomeUncertain,
    CommitRequest,
    CommitResult,
    CommitStatus,
)
from .ports import CommitRepository


class ApplicationCommitter:
    """Prepara un commit senza clock, retry o I/O diretto."""

    def __init__(self, repository: CommitRepository) -> None:
        self._repository = repository

    def prepare(self, request: CommitRequest) -> CommitResult:
        if not isinstance(request, CommitRequest):
            raise InvalidCommitRequestError(
                "request deve essere una CommitRequest valida."
            )
        plan = request.validated_plan
        self._repository.prepare_commit(request)
        return CommitResult(
            run_id=plan.plan.run_id,
            commit_started_at=request.requested_at,
            target_name=plan.target_name,
            expected_operations=plan.plan.expected_logical_row_count,
            status=CommitStatus.PREPARED,
        )

    def commit(self, request: CommitRequest) -> CommitResult:
        if not isinstance(request, CommitRequest):
            raise InvalidCommitRequestError(
                "request deve essere una CommitRequest valida."
            )
        outcome = self._repository.execute_commit(request)
        if isinstance(outcome, CommitOutcomeUncertain):
            expected = request.validated_plan.plan
            if (
                outcome.run_id != expected.run_id
                or outcome.requested_at != request.requested_at
                or outcome.idempotency_keys != expected.idempotency_keys
                or outcome.expected_record_count != expected.expected_record_count
                or outcome.expected_logical_row_count
                != expected.expected_logical_row_count
                or outcome.correlation_id != request.correlation_id
            ):
                raise CommitReceiptMismatchError(
                    "L'outcome incerto non coincide con la richiesta."
                )
            return CommitResult(
                run_id=expected.run_id,
                commit_started_at=request.requested_at,
                target_name=request.validated_plan.target_name,
                expected_operations=expected.expected_logical_row_count,
                status=CommitStatus.RECONCILIATION_REQUIRED,
                reconciliation_context=outcome,
            )
        receipt = outcome
        if not isinstance(receipt, CommitExecutionReceipt):
            raise CommitReceiptMismatchError(
                "Il repository non ha restituito una CommitExecutionReceipt."
            )
        plan = request.validated_plan
        expected = plan.plan
        mismatches = (
            receipt.run_id != expected.run_id,
            receipt.target_name != plan.target_name,
            receipt.expected_record_count != expected.expected_record_count,
            receipt.expected_logical_row_count
            != expected.expected_logical_row_count,
        )
        if any(mismatches):
            raise CommitReceiptMismatchError(
                "La ricevuta non coincide con il piano validato."
            )
        if receipt.commit_completed_at.datetime < request.requested_at.datetime:
            raise CommitReceiptMismatchError(
                "La ricevuta precede la richiesta di commit."
            )
        reconciled_set = set(receipt.reconciled_idempotency_keys)
        if not reconciled_set.issubset(expected.idempotency_keys):
            raise CommitReceiptMismatchError(
                "La ricevuta contiene chiavi estranee al piano validato."
            )
        if receipt.reconciliation_complete and (
            receipt.reconciled_idempotency_keys != expected.idempotency_keys
        ):
            raise CommitReceiptMismatchError(
                "La riconciliazione completa non coincide con le chiavi del piano."
            )
        reconciliation_context = None
        if not receipt.reconciliation_complete:
            reconciliation_context = CommitOutcomeUncertain(
                run_id=expected.run_id,
                requested_at=request.requested_at,
                idempotency_keys=expected.idempotency_keys,
                expected_record_count=expected.expected_record_count,
                expected_logical_row_count=expected.expected_logical_row_count,
                correlation_id=request.correlation_id,
            )
        return CommitResult(
            run_id=expected.run_id,
            commit_started_at=request.requested_at,
            target_name=plan.target_name,
            expected_operations=expected.expected_logical_row_count,
            status=(
                CommitStatus.COMMITTED
                if receipt.reconciliation_complete
                else CommitStatus.RECONCILIATION_REQUIRED
            ),
            committed_operations=(
                receipt.appended_physical_row_count
                if receipt.reconciliation_complete
                else None
            ),
            reconciled_idempotency_keys=receipt.reconciled_idempotency_keys,
            commit_completed_at=(
                receipt.commit_completed_at
                if receipt.reconciliation_complete
                else None
            ),
            reconciliation_context=reconciliation_context,
        )
