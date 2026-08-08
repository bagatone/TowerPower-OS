from dataclasses import FrozenInstanceError
from datetime import date, datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.committer import (
    CommitExecutionContext,
    CommitRequest,
    CommitResult,
    CommitStatus,
)
from src.tpo_core.application.operational_scheduling import (
    ExecuteSchedulingCommit,
    ExecuteSchedulingCommitInput,
    OperationalSchedulingCommitError,
)
from src.tpo_core.application.run_tracking import (
    OpenSchedulingRun,
    SchedulingRunCompletion,
)
from src.tpo_core.application.scheduling.models import (
    ScheduledOrderRecord,
    SchedulingResult,
)
from src.tpo_core.application.scheduling.provenance import OrderLineProvenance
from src.tpo_core.application.write_plan import (
    WRITE_SCHEMA_ORDINI,
    WRITE_SCHEMA_VERSION,
    WRITE_TARGET_ORDINI,
    ValidatedWritePlan,
    WritePlanBuilder,
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


def instant(hour: int) -> CurrentSystemDate:
    return CurrentSystemDate(datetime(2026, 8, 8, hour, tzinfo=TZ))


def scheduling_result(state: RunState = RunState.SUCCESS) -> SchedulingResult:
    program_id = ProgrammaFornituraId("PF-000001")
    record = ScheduledOrderRecord(
        ordine=Ordine(
            id=OrdineId("ORD-000001"),
            cliente_id=ClienteId("CLI-000001"),
            data_ordine=date(2026, 8, 8),
            righe=(
                RigaOrdine(
                    VarietaId("VAR-000001"),
                    Quantity(1, UnitOfMeasure.SET),
                ),
            ),
            stato=OrdineState.APERTO,
            tipo_creazione=OrdineCreationType.AUTOMATICO,
            programma_fornitura_id=program_id,
        ),
        data_consegna_prevista=date(2026, 8, 9),
        chiave_idempotenza="key-1",
        provenance=(OrderLineProvenance(program_id, 1, 1, 1),),
    )
    return SchedulingResult(
        run_id=RunId("RUN-000001"),
        ordini_generati=(record,),
        anteprime=(),
        programmi_letti=1,
        righe_valutate=1,
        occorrenze_valutate=1,
        occorrenze_generate=1,
        occorrenze_saltate_per_idempotenza=0,
        avvisi=(),
        simulation=False,
        esito=state,
    )


def request(*, simulation: bool = False) -> ExecuteSchedulingCommitInput:
    return ExecuteSchedulingCommitInput(
        open_run=OpenSchedulingRun(
            RunId("RUN-000001"), instant(5), simulation, version=2
        ),
        current_system_date=instant(6),
        completion_at=instant(7),
        requested_at=instant(8),
        commit_completed_at=instant(9),
        execution_context=CommitExecutionContext(
            ActorId("scheduler"), "scheduled orders", "correlation-1"
        ),
    )


def dependencies(*, result=None, commit_status=CommitStatus.COMMITTED):
    result = result or scheduling_result()
    completion = SchedulingRunCompletion(
        run_id=result.run_id,
        started_at=instant(5),
        completed_at=instant(7),
        simulation=False,
        expected_version=2,
        final_state=result.esito,
        programmi_letti=1,
        righe_valutate=1,
        occorrenze_valutate=1,
        ordini_generati=1,
        elementi_saltati=0,
        warnings=(),
        errors=(),
    )
    plan = WritePlanBuilder().build(
        scheduling_result=result,
        open_run=request().open_run,
        completion=completion,
    )
    validated = ValidatedWritePlan(
        plan=plan,
        validated_at=instant(7),
        existing_idempotency_keys_checked=(),
        target_name=WRITE_TARGET_ORDINI,
        expected_schema_name=WRITE_SCHEMA_ORDINI,
        expected_schema_version=WRITE_SCHEMA_VERSION,
        validation_snapshot=WritePlanValidationSnapshot(
            run_id=plan.run_id,
            expected_record_count=1,
            expected_logical_row_count=1,
            checked_existing_key_count=0,
            schema_name=WRITE_SCHEMA_ORDINI,
            schema_version=WRITE_SCHEMA_VERSION,
            target_name=WRITE_TARGET_ORDINI,
        ),
    )
    commit_result = CommitResult(
        run_id=result.run_id,
        commit_started_at=instant(8),
        target_name=WRITE_TARGET_ORDINI,
        expected_operations=1,
        status=commit_status,
        committed_operations=1,
        reconciled_idempotency_keys=("key-1",),
        commit_completed_at=instant(9),
    )
    run_scheduling = Mock()
    run_scheduling.execute.return_value = result
    run_service = Mock()
    run_service.propose_completion.return_value = completion
    builder = Mock()
    builder.build.return_value = plan
    validator = Mock()
    validator.validate.return_value = validated
    committer = Mock()
    committer.commit.return_value = commit_result
    use_case = ExecuteSchedulingCommit(
        run_scheduling, run_service, builder, validator, committer
    )
    return use_case, run_scheduling, run_service, builder, validator, committer


def test_percorso_operativo_preserva_input_output_e_chiamate() -> None:
    use_case, scheduling, runs, builder, validator, committer = dependencies()
    source = request()
    output = use_case.execute(source)

    scheduling.execute.assert_called_once_with(
        run_id=source.open_run.run_id,
        current_system_date=source.current_system_date,
        simulation=False,
    )
    runs.propose_completion.assert_called_once()
    assert runs.complete_run.call_count == 0
    assert runs.fail_run.call_count == 0
    builder.build.assert_called_once()
    validator.validate.assert_called_once()
    commit_request = committer.commit.call_args.args[0]
    assert isinstance(commit_request, CommitRequest)
    assert commit_request.requested_at is source.requested_at
    assert commit_request.execution_context is source.execution_context
    assert committer.commit.call_args.args[1] is source.commit_completed_at
    assert output.scheduling_result is scheduling.execute.return_value
    assert output.commit_result is committer.commit.return_value
    assert output.completed_run.completed_at == source.completion_at
    assert output.completed_run.version == source.open_run.version + 1
    with pytest.raises(FrozenInstanceError):
        source.requested_at = instant(10)


def test_sequenza_esatta_e_completed_run_solo_dopo_commit() -> None:
    use_case, scheduling, runs, builder, validator, committer = dependencies()
    calls = []
    scheduling.execute.side_effect = lambda **_: calls.append("schedule") or scheduling_result()
    original_completion = runs.propose_completion.return_value
    runs.propose_completion.side_effect = lambda **_: calls.append("completion") or original_completion
    original_plan = builder.build.return_value
    builder.build.side_effect = lambda **_: calls.append("build") or original_plan
    original_validated = validator.validate.return_value
    validator.validate.side_effect = lambda **_: calls.append("validate") or original_validated
    original_commit = committer.commit.return_value
    committer.commit.side_effect = lambda *_: calls.append("commit") or original_commit

    output = use_case.execute(request())
    calls.append("completed" if output.completed_run else "missing")
    assert calls == ["schedule", "completion", "build", "validate", "commit", "completed"]


def test_simulazione_rifiutata_prima_dello_scheduling() -> None:
    use_case, scheduling, _, _, _, committer = dependencies()
    with pytest.raises(OperationalSchedulingCommitError, match="simulazione"):
        use_case.execute(request(simulation=True))
    scheduling.execute.assert_not_called()
    committer.commit.assert_not_called()


def test_failed_non_costruisce_piano_e_non_committta() -> None:
    failed = scheduling_result(RunState.FAILED)
    use_case, scheduling, runs, builder, validator, committer = dependencies()
    scheduling.execute.return_value = failed
    with pytest.raises(OperationalSchedulingCommitError, match="FAILED"):
        use_case.execute(request())
    runs.propose_completion.assert_not_called()
    builder.build.assert_not_called()
    validator.validate.assert_not_called()
    committer.commit.assert_not_called()


@pytest.mark.parametrize("failing_dependency", ["schedule", "validate", "commit"])
def test_errori_propagati_senza_retry(failing_dependency: str) -> None:
    use_case, scheduling, _, _, validator, committer = dependencies()
    dependency = {"schedule": scheduling, "validate": validator, "commit": committer}[
        failing_dependency
    ]
    method = dependency.execute if failing_dependency == "schedule" else (
        dependency.validate if failing_dependency == "validate" else dependency.commit
    )
    method.side_effect = RuntimeError(failing_dependency)
    with pytest.raises(RuntimeError, match=failing_dependency):
        use_case.execute(request())
    assert method.call_count == 1
    assert committer.commit.call_count <= 1


def test_risultato_non_riconciliato_non_materializza_completed_run() -> None:
    use_case, _, _, _, _, committer = dependencies(
        commit_status=CommitStatus.RECONCILIATION_REQUIRED
    )
    with pytest.raises(OperationalSchedulingCommitError, match="conferma"):
        use_case.execute(request())
    assert committer.commit.call_count == 1
