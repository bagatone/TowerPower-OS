from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from src.tpo_core.application.committer import (
    CommitExecutionContext,
    CommitExecutionError,
    CommitOutcomeUncertain,
    CommitPreparationError,
    CommitResult,
    CommitStatus,
)
from src.tpo_core.application.operational_scheduling import (
    ExecuteSchedulingCommitResult,
    OperationalSchedulingInput,
    OperationalSchedulingOrchestrator,
    OperationalSchedulingStatus,
)
from src.tpo_core.application.run_tracking import (
    CompletedSchedulingRun,
    OpenSchedulingRun,
)
from src.tpo_core.application.scheduling.models import SchedulingResult
from src.tpo_core.application.write_plan import WritePlanValidationError
from src.tpo_core.domain.identifiers import ActorId, RunId
from src.tpo_core.domain.states import RunState
from src.tpo_core.domain.time_reference import CurrentSystemDate


TZ = ZoneInfo("Atlantic/Canary")


def instant(hour: int) -> CurrentSystemDate:
    return CurrentSystemDate(datetime(2026, 8, 9, hour, tzinfo=TZ))


def context() -> CommitExecutionContext:
    return CommitExecutionContext(
        ActorId("scheduler"), "operational scheduling", "run-correlation"
    )


def scheduling(run_id: RunId, state: RunState = RunState.SUCCESS):
    return SchedulingResult(
        run_id=run_id,
        ordini_generati=(),
        anteprime=(),
        programmi_letti=1,
        righe_valutate=1,
        occorrenze_valutate=1,
        occorrenze_generate=1,
        occorrenze_saltate_per_idempotenza=0,
        avvisi=("warning",) if state is RunState.FAILED else (),
        simulation=False,
        esito=state,
    )


def completed(run: OpenSchedulingRun, state: RunState = RunState.SUCCESS):
    return CompletedSchedulingRun(
        run_id=run.run_id,
        started_at=run.started_at,
        completed_at=instant(9),
        simulation=False,
        state=state,
        programmi_letti=1 if state is not RunState.FAILED else 0,
        righe_valutate=1 if state is not RunState.FAILED else 0,
        occorrenze_valutate=1 if state is not RunState.FAILED else 0,
        ordini_generati=1 if state is not RunState.FAILED else 0,
        elementi_saltati=0,
        warnings=(),
        errors=("failure",) if state is RunState.FAILED else (),
        version=1,
    )


class FakeClock:
    def __init__(self, trace):
        self.trace = trace
        self.values = iter((instant(5), instant(7), instant(8), instant(9)))

    def now(self):
        value = next(self.values)
        self.trace.append(f"clock:{value.datetime.hour}")
        return value


class FakeAllocator:
    def __init__(self, trace):
        self.trace = trace
        self.calls = 0

    def allocate(self, identifier_type):
        self.calls += 1
        self.trace.append("allocate")
        return SimpleNamespace(identifier=RunId("RUN-000001"))


class FakeRunService:
    def __init__(self, trace):
        self.trace = trace
        self.opened = None
        self.current = None
        self.fail_calls = []
        self.fail_error = None

    def open_run(self, *, run_id, started_at, simulation):
        self.trace.append("open")
        self.opened = OpenSchedulingRun(run_id, started_at, simulation)
        self.current = self.opened
        return self.opened

    def get_run(self, run_id):
        self.trace.append("get")
        return self.current

    def fail_run(self, **values):
        self.trace.append("fail")
        self.fail_calls.append(values)
        if self.fail_error is not None:
            raise self.fail_error
        failed = CompletedSchedulingRun(
            run_id=values["open_run"].run_id,
            started_at=values["open_run"].started_at,
            completed_at=values["completed_at"],
            simulation=False,
            state=RunState.FAILED,
            programmi_letti=0,
            righe_valutate=0,
            occorrenze_valutate=0,
            ordini_generati=0,
            elementi_saltati=0,
            warnings=values["warnings"],
            errors=values["errors"],
            version=1,
        )
        self.current = failed
        return failed


class FakeScheduling:
    def __init__(self, trace, state=RunState.SUCCESS):
        self.trace = trace
        self.state = state
        self.calls = 0
        self.error = None

    def execute(self, **values):
        self.calls += 1
        self.trace.append("scheduling")
        if self.error is not None:
            raise self.error
        return scheduling(values["run_id"], self.state)


class FakeExecuteCommit:
    def __init__(self, trace, clock, *, status=CommitStatus.COMMITTED, error=None):
        self.trace = trace
        self.clock = clock
        self.status = status
        self.error = error
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        self.trace.append("commit-flow")
        scheduling_result = request.scheduling_result
        completion_at = self.clock.now()
        requested_at = self.clock.now()
        if self.error is not None:
            raise self.error
        uncertain = self.status is CommitStatus.RECONCILIATION_REQUIRED
        reconciliation = (
            CommitOutcomeUncertain(
                run_id=request.open_run.run_id,
                requested_at=requested_at,
                idempotency_keys=("key-1",),
                expected_record_count=1,
                expected_logical_row_count=1,
                correlation_id=request.execution_context.correlation_id,
            )
            if uncertain
            else None
        )
        commit_result = CommitResult(
            run_id=request.open_run.run_id,
            commit_started_at=requested_at,
            target_name="ORDINI",
            expected_operations=1,
            status=self.status,
            committed_operations=None if uncertain else 1,
            reconciled_idempotency_keys=() if uncertain else ("key-1",),
            commit_completed_at=None if uncertain else instant(9),
            reconciliation_context=reconciliation,
        )
        return ExecuteSchedulingCommitResult(
            scheduling_result=scheduling_result,
            commit_result=commit_result,
            completed_run=(
                None
                if uncertain
                else CompletedSchedulingRun(
                    request.open_run.run_id,
                    request.open_run.started_at,
                    completion_at,
                    False,
                    RunState.SUCCESS,
                    1, 1, 1, 1, 0, (), (), 1,
                )
            ),
        )


def dependencies(*, state=RunState.SUCCESS, status=CommitStatus.COMMITTED, error=None):
    trace = []
    clock = FakeClock(trace)
    allocator = FakeAllocator(trace)
    runs = FakeRunService(trace)
    scheduler = FakeScheduling(trace, state)
    execute_commit = FakeExecuteCommit(trace, clock, status=status, error=error)
    target = OperationalSchedulingOrchestrator(
        allocator, runs, scheduler, execute_commit, clock
    )
    return target, allocator, runs, scheduler, execute_commit, trace


def request() -> OperationalSchedulingInput:
    return OperationalSchedulingInput(instant(6), context())


def test_happy_path_apre_e_conclude_run_con_ordering_temporale() -> None:
    target, allocator, runs, scheduler, execute_commit, trace = dependencies()
    result = target.execute(request())
    assert result.status is OperationalSchedulingStatus.COMMITTED
    assert result.completed_run is not None
    assert result.open_run.started_at == instant(5)
    assert allocator.calls == scheduler.calls == execute_commit.calls == 1
    assert runs.fail_calls == []
    assert trace == [
        "allocate", "clock:5", "open", "scheduling", "commit-flow",
        "clock:7", "clock:8",
    ]


def test_scheduling_failed_conclude_run_failed_una_volta() -> None:
    target, _, runs, _, execute_commit, _ = dependencies(state=RunState.FAILED)
    result = target.execute(request())
    assert result.status is OperationalSchedulingStatus.FAILED
    assert result.completed_run.state is RunState.FAILED
    assert result.scheduling_result.esito is RunState.FAILED
    assert len(runs.fail_calls) == 1
    assert execute_commit.calls == 0


def test_validation_failure_certa_conclude_run_failed() -> None:
    target, _, runs, _, _, _ = dependencies(error=WritePlanValidationError("schema"))
    result = target.execute(request())
    assert result.status is OperationalSchedulingStatus.FAILED
    assert result.errors == ("schema",)
    assert result.scheduling_result is not None
    assert len(runs.fail_calls) == 1


def test_preparation_failure_certa_conclude_run_failed() -> None:
    target, _, runs, _, _, _ = dependencies(
        error=CommitPreparationError("preparazione")
    )
    result = target.execute(request())
    assert result.status is OperationalSchedulingStatus.FAILED
    assert result.errors == ("preparazione",)
    assert len(runs.fail_calls) == 1


def test_commit_failure_certa_conclude_run_failed() -> None:
    target, _, runs, _, execute_commit, _ = dependencies(
        error=CommitExecutionError("commit certo")
    )
    result = target.execute(request())
    assert result.status is OperationalSchedulingStatus.FAILED
    assert result.primary_error is execute_commit.error
    assert len(runs.fail_calls) == 1


def test_reconciliation_non_conclude_run_e_preserva_context() -> None:
    target, _, runs, _, _, _ = dependencies(
        status=CommitStatus.RECONCILIATION_REQUIRED
    )
    result = target.execute(request())
    assert result.status is OperationalSchedulingStatus.RECONCILIATION_REQUIRED
    assert result.completed_run is None
    assert result.commit_result.reconciliation_context.correlation_id == "run-correlation"
    assert runs.fail_calls == []


def test_run_gia_conclusa_non_chiama_fail_run() -> None:
    target, _, runs, _, _, _ = dependencies(
        error=CommitExecutionError("run conclusa")
    )
    original_get = runs.get_run

    def completed_get(run_id):
        runs.current = completed(runs.opened)
        return original_get(run_id)

    runs.get_run = completed_get
    result = target.execute(request())
    assert result.status is OperationalSchedulingStatus.FAILED
    assert result.completed_run is runs.current
    assert result.finalization_error is None
    assert runs.fail_calls == []


def test_failure_finalization_non_maschera_errore_primario_e_non_ritenta() -> None:
    target, _, runs, _, execute_commit, _ = dependencies(
        error=CommitExecutionError("primario")
    )
    runs.fail_error = RuntimeError("finalizzazione")
    result = target.execute(request())
    assert result.primary_error is execute_commit.error
    assert result.finalization_error is runs.fail_error
    assert len(runs.fail_calls) == 1


def test_scheduling_exception_pre_write_conclude_run_failed_senza_retry() -> None:
    target, _, runs, scheduler, execute_commit, _ = dependencies()
    primary = RuntimeError("scheduling inatteso")
    scheduler.error = primary

    result = target.execute(request())

    assert result.status is OperationalSchedulingStatus.FAILED
    assert result.primary_error is primary
    assert result.scheduling_result is None
    assert scheduler.calls == 1
    assert len(runs.fail_calls) == 1
    assert execute_commit.calls == 0


def test_version_conflict_non_conclude_run_e_non_ritenta() -> None:
    target, _, runs, _, execute_commit, _ = dependencies(
        error=CommitExecutionError("primario")
    )
    original_get = runs.get_run

    def conflicting_get(run_id):
        runs.current = OpenSchedulingRun(
            runs.opened.run_id,
            runs.opened.started_at,
            runs.opened.simulation,
            version=runs.opened.version + 1,
        )
        return original_get(run_id)

    runs.get_run = conflicting_get
    result = target.execute(request())

    assert result.status is OperationalSchedulingStatus.FAILED
    assert result.primary_error is execute_commit.error
    assert result.finalization_error is not None
    assert runs.fail_calls == []
    assert execute_commit.calls == 1
