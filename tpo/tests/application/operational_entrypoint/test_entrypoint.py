from dataclasses import fields
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.committer import CommitOutcomeUncertain
import src.tpo_core.application.operational_entrypoint as public_entrypoint
from src.tpo_core.application.operational_entrypoint import (
    OperationalSchedulingEntryPoint,
    OperationalSchedulingIntent,
    OperationalReconciliationContext,
    RecognizedOperationalIdentity,
)
from src.tpo_core.application.operational_entrypoint.context import (
    OPERATIONAL_SCHEDULING_REASON,
    OperationalExecutionContextFactory,
)
from src.tpo_core.application.operational_scheduling import (
    OperationalSchedulingStatus,
)
from src.tpo_core.application.run_tracking import (
    CompletedSchedulingRun,
    OpenSchedulingRun,
)
from src.tpo_core.domain.identifiers import ActorId, RunId
from src.tpo_core.domain.states import RunState
from src.tpo_core.domain.time_reference import CurrentSystemDate


TZ = ZoneInfo("Atlantic/Canary")


def instant(hour: int) -> CurrentSystemDate:
    return CurrentSystemDate(datetime(2026, 8, 10, hour, tzinfo=TZ))


class FixedCorrelationIdGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self) -> str:
        self.calls += 1
        return "correlation-entrypoint-1"


class FakeOrchestrator:
    def __init__(self, status: OperationalSchedulingStatus) -> None:
        self.status = status
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        open_run = OpenSchedulingRun(RunId("RUN-000001"), instant(5), False)
        completed_run = None
        errors = ()
        primary_error = None
        commit_result = None
        if self.status is OperationalSchedulingStatus.COMMITTED:
            completed_run = CompletedSchedulingRun(
                run_id=open_run.run_id,
                started_at=open_run.started_at,
                completed_at=instant(7),
                simulation=False,
                state=RunState.SUCCESS,
                programmi_letti=1,
                righe_valutate=1,
                occorrenze_valutate=1,
                ordini_generati=1,
                elementi_saltati=0,
                warnings=(),
                errors=(),
                version=1,
            )
            commit_result = SimpleNamespace(reconciliation_context=None)
        elif self.status is OperationalSchedulingStatus.FAILED:
            errors = ("failure",)
            primary_error = RuntimeError("failure")
        else:
            commit_result = SimpleNamespace(
                reconciliation_context=CommitOutcomeUncertain(
                    run_id=open_run.run_id,
                    requested_at=instant(7),
                    idempotency_keys=("key-1",),
                    expected_record_count=1,
                    expected_logical_row_count=1,
                    correlation_id=request.execution_context.correlation_id,
                    technical_cause=RuntimeError("provider detail"),
                )
            )
        return SimpleNamespace(
            status=self.status,
            open_run=open_run,
            completed_run=completed_run,
            commit_result=commit_result,
            errors=errors,
            warnings=("warning",),
            primary_error=primary_error,
        )


def test_context_factory_costruisce_actor_reason_e_correlation_id() -> None:
    generator = FixedCorrelationIdGenerator()
    factory = OperationalExecutionContextFactory(generator)

    context = factory.create(RecognizedOperationalIdentity("operator-1"))

    assert context.actor == ActorId("operator-1")
    assert context.reason == OPERATIONAL_SCHEDULING_REASON
    assert context.correlation_id == "correlation-entrypoint-1"
    assert generator.calls == 1


def test_intenzione_pubblica_non_espone_protocollo_commit() -> None:
    assert {field.name for field in fields(OperationalSchedulingIntent)} == {
        "business_date",
        "operational_identity",
    }
    assert set(public_entrypoint.__all__) == {
        "OperationalEntryPointResult",
        "OperationalReconciliationContext",
        "OperationalSchedulingEntryPoint",
        "OperationalSchedulingIntent",
        "RecognizedOperationalIdentity",
    }


@pytest.mark.parametrize(
    "status",
    (
        OperationalSchedulingStatus.COMMITTED,
        OperationalSchedulingStatus.FAILED,
        OperationalSchedulingStatus.RECONCILIATION_REQUIRED,
    ),
)
def test_entrypoint_costruisce_input_invoca_una_volta_e_propaga_outcome(
    status: OperationalSchedulingStatus,
) -> None:
    generator = FixedCorrelationIdGenerator()
    orchestrator = FakeOrchestrator(status)
    target = OperationalSchedulingEntryPoint(
        OperationalExecutionContextFactory(generator), orchestrator
    )
    intent = OperationalSchedulingIntent(
        business_date=instant(6),
        operational_identity=RecognizedOperationalIdentity("operator-1"),
    )

    result = target.execute(intent)

    assert len(orchestrator.calls) == 1
    request = orchestrator.calls[0]
    assert request.current_system_date is intent.business_date
    assert request.execution_context.actor == ActorId("operator-1")
    assert request.execution_context.reason == OPERATIONAL_SCHEDULING_REASON
    assert request.execution_context.correlation_id == "correlation-entrypoint-1"
    assert generator.calls == 1
    assert result.status is status
    assert result.run_id == RunId("RUN-000001")
    assert result.warnings == ("warning",)
    assert "execution_context" not in {
        field.name for field in fields(type(result))
    }
    if status is OperationalSchedulingStatus.COMMITTED:
        assert result.completed_run is not None
        assert result.reconciliation_context is None
    elif status is OperationalSchedulingStatus.FAILED:
        assert result.completed_run is None
        assert result.errors == ("failure",)
        assert result.reconciliation_context is None
    else:
        assert result.completed_run is None
        assert result.reconciliation_context is not None
        assert isinstance(
            result.reconciliation_context, OperationalReconciliationContext
        )
        assert (
            result.reconciliation_context.correlation_id
            == "correlation-entrypoint-1"
        )
        assert not hasattr(result.reconciliation_context, "technical_cause")
        assert not any(
            isinstance(value, BaseException)
            for value in vars(result.reconciliation_context).values()
        )
