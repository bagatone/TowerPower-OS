from dataclasses import FrozenInstanceError
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.committer import (
    ApplicationCommitter,
    CommitExecutionReceipt,
    CommitReceiptMismatchError,
    CommitRequest,
    CommitStatus,
    InvalidCommitRequestError,
)
from src.tpo_core.application.scheduling.models import ScheduledOrderRecord
from src.tpo_core.application.write_plan import (
    ValidatedWritePlan,
    WritePlan,
    WritePlanValidationSnapshot,
)
from src.tpo_core.domain.entities.ordine import Ordine, RigaOrdine
from src.tpo_core.domain.identifiers import (
    ClienteId,
    OrdineId,
    ProgrammaFornituraId,
    RunId,
    VarietaId,
)
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import OrdineState
from src.tpo_core.domain.time_reference import CurrentSystemDate


TZ = ZoneInfo("Atlantic/Canary")


def instant(hour):
    return CurrentSystemDate(datetime(2026, 8, 3, hour, tzinfo=TZ))


def validated_plan(*, two_lines=False):
    lines = (
        RigaOrdine(
            VarietaId("VAR-000001"),
            Quantity(2, UnitOfMeasure.SET),
        ),
    )
    if two_lines:
        lines += (
            RigaOrdine(
                VarietaId("VAR-000002"),
                Quantity(3, UnitOfMeasure.GRAM),
            ),
        )
    record = ScheduledOrderRecord(
        Ordine(
            OrdineId("ORD-000001"),
            ClienteId("CLI-000001"),
            date(2026, 8, 3),
            lines,
            OrdineState.APERTO,
            ProgrammaFornituraId("PF-000001"),
        ),
        date(2026, 8, 6),
        "key-001",
    )
    plan = WritePlan(
        RunId("RUN-000001"),
        instant(6),
        (record,),
        1,
        len(lines),
        ("key-001",),
        ("warning",),
    )
    snapshot = WritePlanValidationSnapshot(
        run_id=plan.run_id,
        expected_record_count=1,
        expected_logical_row_count=len(lines),
        checked_existing_key_count=1,
        schema_name="ORDINI",
        schema_version="1.0",
        target_name="ORDINI",
    )
    return ValidatedWritePlan(
        plan=plan,
        validated_at=instant(7),
        existing_idempotency_keys_checked=("existing",),
        target_name="ORDINI",
        expected_schema_name="ORDINI",
        expected_schema_version="1.0",
        validation_snapshot=snapshot,
        warnings=plan.warnings,
    )


class FakeCommitRepository:
    def __init__(self, error=None, receipt=None):
        self.error = error
        self.receipt = receipt
        self.calls = []
        self.execute_calls = []

    def prepare_commit(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error

    def execute_commit(self, request, completed_at):
        self.execute_calls.append((request, completed_at))
        if self.error is not None:
            raise self.error
        return self.receipt


def execution_receipt(plan, completed_at, *, complete=True, **overrides):
    write_plan = plan.plan
    values = {
        "run_id": write_plan.run_id,
        "target_name": plan.target_name,
        "expected_record_count": write_plan.expected_record_count,
        "expected_logical_row_count": write_plan.expected_logical_row_count,
        "appended_physical_row_count": write_plan.expected_logical_row_count,
        "reconciled_idempotency_keys": (
            write_plan.idempotency_keys if complete else ()
        ),
        "commit_completed_at": completed_at,
        "reconciliation_complete": complete,
    }
    values.update(overrides)
    return CommitExecutionReceipt(**values)


def test_prepare_valido_e_risultato_corretto() -> None:
    repository = FakeCommitRepository()
    plan = validated_plan()
    requested_at = instant(8)
    request = CommitRequest(plan, requested_at)
    result = ApplicationCommitter(repository).prepare(request)
    assert result.run_id == RunId("RUN-000001")
    assert result.commit_started_at is requested_at
    assert result.target_name == "ORDINI"
    assert result.expected_operations == 1
    assert result.status is CommitStatus.PREPARED


def test_requested_at_uguale_a_validated_at_accettato() -> None:
    plan = validated_plan()
    request = CommitRequest(plan, plan.validated_at)
    result = ApplicationCommitter(FakeCommitRepository()).prepare(request)
    assert result.commit_started_at == plan.validated_at


def test_requested_at_successivo_a_validated_at_accettato() -> None:
    plan = validated_plan()
    request = CommitRequest(plan, instant(8))
    result = ApplicationCommitter(FakeCommitRepository()).prepare(request)
    assert result.commit_started_at == instant(8)


def test_requested_at_precedente_a_validated_at_rifiutato() -> None:
    with pytest.raises(
        InvalidCommitRequestError,
        match="requested_at non può precedere validated_at",
    ):
        CommitRequest(validated_plan(), instant(6))


def test_repository_non_chiamato_per_richiesta_temporalmente_invalida() -> None:
    repository = FakeCommitRepository()
    committer = ApplicationCommitter(repository)
    with pytest.raises(InvalidCommitRequestError):
        request = CommitRequest(validated_plan(), instant(6))
        committer.prepare(request)
    assert repository.calls == []


def test_expected_operations_rappresenta_le_righe_logiche() -> None:
    request = CommitRequest(validated_plan(two_lines=True), instant(8))
    result = ApplicationCommitter(FakeCommitRepository()).prepare(request)
    assert result.expected_operations == 2


def test_repository_chiamato_una_sola_volta_e_piano_immutato() -> None:
    repository = FakeCommitRepository()
    plan = validated_plan()
    before = plan
    request = CommitRequest(plan, instant(8))
    ApplicationCommitter(repository).prepare(request)
    assert repository.calls == [request]
    assert plan == before


def test_errore_repository_propagato_senza_retry() -> None:
    expected = RuntimeError("repository")
    repository = FakeCommitRepository(expected)
    request = CommitRequest(validated_plan(), instant(8))
    with pytest.raises(RuntimeError, match="repository"):
        ApplicationCommitter(repository).prepare(request)
    assert repository.calls == [request]


def test_richiesta_e_risultato_immutabili() -> None:
    request = CommitRequest(validated_plan(), instant(8))
    result = ApplicationCommitter(FakeCommitRepository()).prepare(request)
    with pytest.raises(FrozenInstanceError):
        request.requested_at = instant(9)
    with pytest.raises(FrozenInstanceError):
        result.status = CommitStatus.PREPARED


def test_commit_valido_restituisce_committed_e_chiama_repository_una_volta() -> None:
    plan = validated_plan(two_lines=True)
    request = CommitRequest(plan, instant(8))
    completed_at = instant(9)
    receipt = execution_receipt(plan, completed_at)
    repository = FakeCommitRepository(receipt=receipt)
    result = ApplicationCommitter(repository).commit(request, completed_at)
    assert repository.execute_calls == [(request, completed_at)]
    assert result.status is CommitStatus.COMMITTED
    assert result.run_id == plan.plan.run_id
    assert result.target_name == "ORDINI"
    assert result.expected_operations == 2
    assert result.committed_operations == 2
    assert result.reconciled_idempotency_keys == ("key-001",)
    assert result.commit_completed_at == completed_at


def test_commit_non_riconciliato_richiede_riconciliazione() -> None:
    plan = validated_plan()
    request = CommitRequest(plan, instant(8))
    completed_at = instant(9)
    repository = FakeCommitRepository(
        receipt=execution_receipt(plan, completed_at, complete=False)
    )
    result = ApplicationCommitter(repository).commit(request, completed_at)
    assert result.status is CommitStatus.RECONCILIATION_REQUIRED
    assert result.reconciled_idempotency_keys == ()


def test_commit_rifiuta_completed_at_precedente_senza_chiamare_repository() -> None:
    plan = validated_plan()
    request = CommitRequest(plan, instant(8))
    repository = FakeCommitRepository()
    with pytest.raises(InvalidCommitRequestError, match="completed_at"):
        ApplicationCommitter(repository).commit(request, instant(7))
    assert repository.execute_calls == []


@pytest.mark.parametrize(
    "override",
    [
        {"run_id": RunId("RUN-999999")},
        {"target_name": "ALTRO"},
        {"expected_record_count": 2},
        {"expected_logical_row_count": 2},
    ],
)
def test_commit_rifiuta_ricevuta_incoerente(override) -> None:
    plan = validated_plan()
    request = CommitRequest(plan, instant(8))
    completed_at = instant(9)
    repository = FakeCommitRepository(
        receipt=execution_receipt(plan, completed_at, **override)
    )
    with pytest.raises(CommitReceiptMismatchError):
        ApplicationCommitter(repository).commit(request, completed_at)
    assert len(repository.execute_calls) == 1


def test_commit_non_assume_corrispondenza_tra_righe_logiche_e_fisiche() -> None:
    plan = validated_plan()
    request = CommitRequest(plan, instant(8))
    completed_at = instant(9)
    repository = FakeCommitRepository(
        receipt=execution_receipt(
            plan,
            completed_at,
            appended_physical_row_count=2,
        )
    )
    result = ApplicationCommitter(repository).commit(request, completed_at)
    assert result.status is CommitStatus.COMMITTED
    assert result.expected_operations == 1
    assert result.committed_operations == 2


def test_commit_propaga_errore_repository_senza_retry() -> None:
    expected = RuntimeError("commit repository")
    plan = validated_plan()
    request = CommitRequest(plan, instant(8))
    repository = FakeCommitRepository(error=expected)
    with pytest.raises(RuntimeError, match="commit repository"):
        ApplicationCommitter(repository).commit(request, instant(9))
    assert len(repository.execute_calls) == 1


@pytest.mark.parametrize(
    "candidate",
    [None, object(), "request"],
)
def test_request_non_valida_rifiutata(candidate) -> None:
    with pytest.raises(InvalidCommitRequestError):
        ApplicationCommitter(FakeCommitRepository()).prepare(candidate)


def test_nessun_clock_infrastruttura_google_o_metodo_di_scrittura() -> None:
    directory = Path("src/tpo_core/application/committer")
    source = "\n".join(path.read_text() for path in directory.glob("*.py"))
    forbidden = (
        "datetime.now",
        "date.today",
        "tpo_core.infrastructure",
        "googleapiclient",
        "GoogleApi",
        "append_rows",
        "batchUpdate",
        "SUCCESS",
    )
    assert all(value not in source for value in forbidden)
