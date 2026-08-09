from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from inspect import signature
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.committer import (
    ApplicationCommitter,
    CommitExecutionContext,
    CommitExecutionReceipt,
    CommitOutcomeUncertain,
    CommitReceiptMismatchError,
    CommitRequest,
    CommitStatus,
    InvalidCommitRequestError,
)
from src.tpo_core.application.scheduling.models import ScheduledOrderRecord
from src.tpo_core.application.run_tracking import SchedulingRunCompletion
from src.tpo_core.application.write_plan import (
    ValidatedWritePlan,
    WritePlan,
    WritePlanValidationSnapshot,
)
from src.tpo_core.domain.entities.ordine import Ordine, RigaOrdine
from src.tpo_core.domain.identifiers import (
    ActorId,
    ClienteId,
    OrdineId,
    ProgrammaFornituraId,
    RunId,
    VarietaId,
)
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import OrdineCreationType, OrdineState, RunState
from src.tpo_core.domain.time_reference import CurrentSystemDate


TZ = ZoneInfo("Atlantic/Canary")


def instant(hour):
    return CurrentSystemDate(datetime(2026, 8, 3, hour, tzinfo=TZ))


def execution_context(**overrides):
    values = {
        "actor": ActorId("actor-test"),
        "reason": "test commit",
        "correlation_id": "correlation-test-001",
    }
    values.update(overrides)
    return CommitExecutionContext(**values)


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
            OrdineCreationType.AUTOMATICO,
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

    def execute_commit(self, request):
        self.execute_calls.append(request)
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


def test_execution_context_valido_immutabile_e_senza_default() -> None:
    context = execution_context()
    assert context.actor == ActorId("actor-test")
    assert context.reason == "test commit"
    assert context.correlation_id == "correlation-test-001"
    assert all(
        parameter.default is parameter.empty
        for parameter in signature(CommitExecutionContext).parameters.values()
    )
    with pytest.raises(FrozenInstanceError):
        context.reason = "altro"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actor", None),
        ("actor", "actor-test"),
        ("reason", None),
        ("reason", ""),
        ("reason", "   "),
        ("reason", " reason"),
        ("reason", "reason "),
        ("correlation_id", None),
        ("correlation_id", ""),
        ("correlation_id", "   "),
        ("correlation_id", " correlation"),
        ("correlation_id", "correlation "),
    ],
)
def test_execution_context_rifiuta_input_invalidi(field, value) -> None:
    with pytest.raises(InvalidCommitRequestError):
        execution_context(**{field: value})


def test_commit_request_richiede_ed_espone_il_contesto_senza_duplicarlo() -> None:
    plan = validated_plan()
    context = execution_context()
    request = CommitRequest(plan, instant(8), context)
    assert request.execution_context is context
    assert request.actor is context.actor
    assert request.audit_reason is context.reason
    assert request.correlation_id is context.correlation_id
    assert set(request.__dict__) == {
        "validated_plan", "requested_at", "execution_context"
    }
    with pytest.raises(TypeError):
        CommitRequest(plan, instant(8))
    with pytest.raises(InvalidCommitRequestError):
        CommitRequest(plan, instant(8), None)


def test_committer_preserva_identita_del_contesto() -> None:
    repository = FakeCommitRepository()
    context = execution_context()
    request = CommitRequest(validated_plan(), instant(8), context)
    ApplicationCommitter(repository).prepare(request)
    assert repository.calls[0] is request
    assert repository.calls[0].execution_context is context


def test_prepare_valido_e_risultato_corretto() -> None:
    repository = FakeCommitRepository()
    plan = validated_plan()
    requested_at = instant(8)
    request = CommitRequest(plan, requested_at, execution_context())
    result = ApplicationCommitter(repository).prepare(request)
    assert result.run_id == RunId("RUN-000001")
    assert result.commit_started_at is requested_at
    assert result.target_name == "ORDINI"
    assert result.expected_operations == 1
    assert result.status is CommitStatus.PREPARED


def test_requested_at_uguale_a_validated_at_accettato() -> None:
    plan = validated_plan()
    request = CommitRequest(plan, plan.validated_at, execution_context())
    result = ApplicationCommitter(FakeCommitRepository()).prepare(request)
    assert result.commit_started_at == plan.validated_at


def test_requested_at_successivo_a_validated_at_accettato() -> None:
    plan = validated_plan()
    request = CommitRequest(plan, instant(8), execution_context())
    result = ApplicationCommitter(FakeCommitRepository()).prepare(request)
    assert result.commit_started_at == instant(8)


def test_requested_at_precedente_a_validated_at_rifiutato() -> None:
    with pytest.raises(
        InvalidCommitRequestError,
        match="requested_at non può precedere validated_at",
    ):
        CommitRequest(validated_plan(), instant(6), execution_context())


def test_repository_non_chiamato_per_richiesta_temporalmente_invalida() -> None:
    repository = FakeCommitRepository()
    committer = ApplicationCommitter(repository)
    with pytest.raises(InvalidCommitRequestError):
        request = CommitRequest(validated_plan(), instant(6), execution_context())
        committer.prepare(request)
    assert repository.calls == []


def test_expected_operations_rappresenta_le_righe_logiche() -> None:
    request = CommitRequest(validated_plan(two_lines=True), instant(8), execution_context())
    result = ApplicationCommitter(FakeCommitRepository()).prepare(request)
    assert result.expected_operations == 2


def test_repository_chiamato_una_sola_volta_e_piano_immutato() -> None:
    repository = FakeCommitRepository()
    plan = validated_plan()
    before = plan
    request = CommitRequest(plan, instant(8), execution_context())
    ApplicationCommitter(repository).prepare(request)
    assert repository.calls == [request]
    assert plan == before


def test_errore_repository_propagato_senza_retry() -> None:
    expected = RuntimeError("repository")
    repository = FakeCommitRepository(expected)
    request = CommitRequest(validated_plan(), instant(8), execution_context())
    with pytest.raises(RuntimeError, match="repository"):
        ApplicationCommitter(repository).prepare(request)
    assert repository.calls == [request]


def test_richiesta_e_risultato_immutabili() -> None:
    request = CommitRequest(validated_plan(), instant(8), execution_context())
    result = ApplicationCommitter(FakeCommitRepository()).prepare(request)
    with pytest.raises(FrozenInstanceError):
        request.requested_at = instant(9)
    with pytest.raises(FrozenInstanceError):
        result.status = CommitStatus.PREPARED


def test_commit_valido_restituisce_committed_e_chiama_repository_una_volta() -> None:
    plan = validated_plan(two_lines=True)
    request = CommitRequest(plan, instant(8), execution_context())
    completed_at = instant(9)
    receipt = execution_receipt(plan, completed_at)
    repository = FakeCommitRepository(receipt=receipt)
    result = ApplicationCommitter(repository).commit(request)
    assert repository.execute_calls == [request]
    assert result.status is CommitStatus.COMMITTED
    assert result.run_id == plan.plan.run_id
    assert result.target_name == "ORDINI"
    assert result.expected_operations == 2
    assert result.committed_operations == 2
    assert result.reconciled_idempotency_keys == ("key-001",)
    assert result.commit_completed_at == completed_at
    assert result.reconciliation_context is None


def test_commit_non_riconciliato_richiede_riconciliazione() -> None:
    plan = validated_plan()
    request = CommitRequest(plan, instant(8), execution_context())
    completed_at = instant(9)
    repository = FakeCommitRepository(
        receipt=execution_receipt(plan, completed_at, complete=False)
    )
    result = ApplicationCommitter(repository).commit(request)
    assert result.status is CommitStatus.RECONCILIATION_REQUIRED
    assert result.reconciled_idempotency_keys == ()
    assert result.committed_operations is None
    assert result.commit_completed_at is None
    assert result.reconciliation_context is not None


def test_outcome_incerto_richiede_riconciliazione_senza_dati_fittizi() -> None:
    plan = validated_plan()
    request = CommitRequest(plan, instant(8), execution_context())
    repository = FakeCommitRepository(
        receipt=CommitOutcomeUncertain(
            run_id=plan.plan.run_id,
            requested_at=request.requested_at,
            idempotency_keys=plan.plan.idempotency_keys,
            expected_record_count=plan.plan.expected_record_count,
            expected_logical_row_count=plan.plan.expected_logical_row_count,
            correlation_id=request.correlation_id,
            technical_cause=RuntimeError("transport"),
        )
    )
    result = ApplicationCommitter(repository).commit(request)
    assert result.status is CommitStatus.RECONCILIATION_REQUIRED
    assert result.committed_operations is None
    assert result.commit_completed_at is None
    assert result.reconciliation_context is repository.receipt
    assert result.reconciliation_context.run_id == plan.plan.run_id
    assert result.reconciliation_context.requested_at == request.requested_at
    assert result.reconciliation_context.correlation_id == request.correlation_id
    assert result.reconciliation_context.idempotency_keys == plan.plan.idempotency_keys
    assert (
        result.reconciliation_context.expected_record_count
        == plan.plan.expected_record_count
    )
    assert (
        result.reconciliation_context.expected_logical_row_count
        == plan.plan.expected_logical_row_count
    )
    assert repository.execute_calls == [request]

    with pytest.raises(InvalidCommitRequestError):
        replace(result, reconciliation_context=None)


@pytest.mark.parametrize(
    "override",
    [
        {"run_id": RunId("RUN-999999")},
        {"requested_at": instant(9)},
        {"correlation_id": "correlation-other"},
        {"idempotency_keys": ("key-other",)},
        {"expected_record_count": 2},
        {"expected_logical_row_count": 2},
    ],
)
def test_commit_rifiuta_outcome_incerto_incoerente(override) -> None:
    plan = validated_plan()
    request = CommitRequest(plan, instant(8), execution_context())
    values = {
        "run_id": plan.plan.run_id,
        "requested_at": request.requested_at,
        "idempotency_keys": plan.plan.idempotency_keys,
        "expected_record_count": plan.plan.expected_record_count,
        "expected_logical_row_count": plan.plan.expected_logical_row_count,
        "correlation_id": request.correlation_id,
    }
    values.update(override)
    repository = FakeCommitRepository(receipt=CommitOutcomeUncertain(**values))
    with pytest.raises(CommitReceiptMismatchError):
        ApplicationCommitter(repository).commit(request)
    assert repository.execute_calls == [request]


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
    request = CommitRequest(plan, instant(8), execution_context())
    completed_at = instant(9)
    repository = FakeCommitRepository(
        receipt=execution_receipt(plan, completed_at, **override)
    )
    with pytest.raises(CommitReceiptMismatchError):
        ApplicationCommitter(repository).commit(request)
    assert len(repository.execute_calls) == 1


def test_commit_non_assume_corrispondenza_tra_righe_logiche_e_fisiche() -> None:
    plan = validated_plan()
    request = CommitRequest(plan, instant(8), execution_context())
    completed_at = instant(9)
    repository = FakeCommitRepository(
        receipt=execution_receipt(
            plan,
            completed_at,
            appended_physical_row_count=2,
        )
    )
    result = ApplicationCommitter(repository).commit(request)
    assert result.status is CommitStatus.COMMITTED
    assert result.expected_operations == 1
    assert result.committed_operations == 2


def test_receipt_congela_unita_distinte_ed_e_immutabile() -> None:
    receipt = CommitExecutionReceipt(
        run_id=RunId("RUN-000001"),
        target_name="ORDINI",
        expected_record_count=1,
        expected_logical_row_count=2,
        appended_physical_row_count=3,
        reconciled_idempotency_keys=("key-001",),
        commit_completed_at=instant(9),
        reconciliation_complete=True,
    )
    assert (
        receipt.expected_record_count,
        receipt.expected_logical_row_count,
        receipt.appended_physical_row_count,
    ) == (1, 2, 3)
    with pytest.raises(FrozenInstanceError):
        receipt.appended_physical_row_count = 4


@pytest.mark.parametrize(
    "field",
    (
        "expected_record_count",
        "expected_logical_row_count",
        "appended_physical_row_count",
    ),
)
def test_receipt_rifiuta_ogni_conteggio_negativo(field) -> None:
    plan = validated_plan()
    with pytest.raises(InvalidCommitRequestError, match=field):
        execution_receipt(plan, instant(9), **{field: -1})


def test_timestamp_del_protocollo_restano_distinti() -> None:
    validated = validated_plan()
    completion = SchedulingRunCompletion(
        run_id=validated.plan.run_id,
        started_at=instant(4),
        completed_at=instant(6),
        simulation=False,
        expected_version=3,
        final_state=RunState.SUCCESS_WITH_WARNINGS,
        programmi_letti=1,
        righe_valutate=1,
        occorrenze_valutate=1,
        ordini_generati=1,
        elementi_saltati=0,
        warnings=validated.plan.warnings,
        errors=(),
    )
    authoritative = replace(
        validated,
        plan=replace(validated.plan, completion=completion),
    )
    request = CommitRequest(authoritative, instant(8), execution_context())
    commit_completed_at = instant(9)
    receipt = execution_receipt(authoritative, commit_completed_at)
    repository = FakeCommitRepository(receipt=receipt)

    result = ApplicationCommitter(repository).commit(request)

    assert request.completion.completed_at == instant(6)
    assert request.requested_at == instant(8)
    assert repository.execute_calls == [request]
    assert result.commit_completed_at == instant(9)


def test_commit_propaga_errore_repository_senza_retry() -> None:
    expected = RuntimeError("commit repository")
    plan = validated_plan()
    request = CommitRequest(plan, instant(8), execution_context())
    repository = FakeCommitRepository(error=expected)
    with pytest.raises(RuntimeError, match="commit repository"):
        ApplicationCommitter(repository).commit(request)
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


def test_commit_request_espone_contesto_atomico_completo() -> None:
    validated = validated_plan()
    completion = SchedulingRunCompletion(
        run_id=validated.plan.run_id,
        started_at=instant(5),
        completed_at=validated.plan.created_at,
        simulation=False,
        expected_version=3,
        final_state=RunState.SUCCESS_WITH_WARNINGS,
        programmi_letti=1,
        righe_valutate=1,
        occorrenze_valutate=1,
        ordini_generati=1,
        elementi_saltati=0,
        warnings=validated.plan.warnings,
        errors=(),
    )
    authoritative_plan = replace(validated.plan, completion=completion)
    authoritative = replace(validated, plan=authoritative_plan)
    request = CommitRequest(authoritative, instant(8), execution_context())
    assert request.completion is completion
    assert request.expected_version == 3
    assert request.completion.completed_at == validated.plan.created_at
    assert request.completion.final_state is RunState.SUCCESS_WITH_WARNINGS
