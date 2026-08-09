from argparse import Namespace
from datetime import datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.operational_entrypoint import (
    OperationalReconciliationContext,
    OperationalSchedulingIntent,
    RecognizedOperationalIdentity,
)
from src.tpo_core.application.operational_scheduling.models import (
    OperationalSchedulingStatus,
)
from src.tpo_core.bootstrap import OperationalRuntimeUnavailableError
from src.tpo_core.cli.exit_codes import OperationalExitCode
from src.tpo_core.cli.operational import (
    OperationalCliDependencies,
    run_operational_scheduling_command,
)
from src.tpo_core.domain.identifiers import RunId
from src.tpo_core.domain.time_reference import CurrentSystemDate


TZ = ZoneInfo("Atlantic/Canary")


def instant(hour: int = 0) -> CurrentSystemDate:
    return CurrentSystemDate(datetime(2026, 8, 10, hour, tzinfo=TZ))


def args(**overrides) -> Namespace:
    values = {
        "settings": "settings.yaml",
        "business_date": "2026-08-09",
        "business_time": "14:35",
        "identity": "operator-1",
        "confirm": True,
    }
    values.update(overrides)
    return Namespace(**values)


def public_result(status: OperationalSchedulingStatus):
    reconciliation = None
    errors = ()
    warnings = ("warning pubblico",)
    completed_run = None
    if status is OperationalSchedulingStatus.FAILED:
        errors = ("failure provider-neutral",)
    elif status is OperationalSchedulingStatus.RECONCILIATION_REQUIRED:
        reconciliation = OperationalReconciliationContext(
            run_id=RunId("RUN-000001"),
            requested_at=instant(2),
            idempotency_keys=("key-1", "key-2"),
            expected_record_count=1,
            expected_logical_row_count=2,
            correlation_id="correlation-public",
        )
    else:
        completed_run = SimpleNamespace(state=SimpleNamespace(value="SUCCESS"))
    return SimpleNamespace(
        status=status,
        run_id=RunId("RUN-000001"),
        completed_run=completed_run,
        errors=errors,
        warnings=warnings,
        reconciliation_context=reconciliation,
    )


class FakeEntryPoint:
    def __init__(self, result) -> None:
        self.result = result
        self.calls = []

    def execute(self, intent):
        self.calls.append(intent)
        return self.result


def execute(*, cli_args=None, status=OperationalSchedulingStatus.COMMITTED, factory_error=None, entry_point=True):
    calls = []
    target = FakeEntryPoint(public_result(status)) if entry_point else None

    def factory(settings_path):
        calls.append(settings_path)
        if factory_error is not None:
            raise factory_error
        return SimpleNamespace(operational_scheduling_entry_point=target)

    stdout = StringIO()
    stderr = StringIO()
    code = run_operational_scheduling_command(
        cli_args or args(),
        stdout=stdout,
        stderr=stderr,
        dependencies=OperationalCliDependencies(application_factory=factory),
    )
    return code, stdout.getvalue(), stderr.getvalue(), calls, target


def test_costruisce_intent_esatto_e_invoca_entrypoint_una_sola_volta() -> None:
    code, output, error, calls, target = execute()

    assert code == OperationalExitCode.OPERATION_COMMITTED == 0
    assert error == ""
    assert calls == ["settings.yaml"]
    assert len(target.calls) == 1
    intent = target.calls[0]
    assert isinstance(intent, OperationalSchedulingIntent)
    assert intent.business_date.date.isoformat() == "2026-08-09"
    assert intent.business_date.time.isoformat() == "14:35:00"
    assert intent.business_date.datetime.tzinfo == TZ
    assert intent.operational_identity == RecognizedOperationalIdentity("operator-1")
    assert "STATUS: COMMITTED" in output
    assert "RUN_ID: RUN-000001" in output
    assert "warning pubblico" in output


@pytest.mark.parametrize(
    "cli_args",
    (
        args(business_date="2026-02-30"),
        args(business_date="20260810"),
        args(business_time="14"),
        args(business_time="24:00"),
        args(identity=""),
        args(identity=" operator-1"),
        args(confirm=False),
    ),
)
def test_input_invalido_non_costruisce_runtime_o_invoca_application(cli_args) -> None:
    code, output, error, calls, target = execute(cli_args=cli_args)

    assert code == OperationalExitCode.OPERATION_INPUT_INVALID == 2
    assert output == ""
    assert "OPERATION_INPUT_INVALID" in error
    assert calls == []
    assert target.calls == []


def test_business_time_2359_valido() -> None:
    code, _, _, _, target = execute(cli_args=args(business_time="23:59"))

    assert code == 0
    assert target.calls[0].business_date.time.isoformat() == "23:59:00"


@pytest.mark.parametrize(
    ("status", "expected_code", "expected_text"),
    (
        (OperationalSchedulingStatus.COMMITTED, 0, "STATUS: COMMITTED"),
        (OperationalSchedulingStatus.FAILED, 1, "failure provider-neutral"),
        (
            OperationalSchedulingStatus.RECONCILIATION_REQUIRED,
            4,
            "CORRELATION_ID: correlation-public",
        ),
    ),
)
def test_outcome_mapping_e_rendering(status, expected_code, expected_text) -> None:
    code, output, error, _, target = execute(status=status)

    assert code == expected_code
    assert error == ""
    assert expected_text in output
    assert len(target.calls) == 1


def test_reconciliation_renderizza_solo_proiezione_pubblica() -> None:
    _, output, _, _, _ = execute(
        status=OperationalSchedulingStatus.RECONCILIATION_REQUIRED
    )

    for expected in (
        "RUN_ID: RUN-000001",
        "REQUESTED_AT:",
        "key-1",
        "EXPECTED_RECORD_COUNT: 1",
        "EXPECTED_LOGICAL_ROW_COUNT: 2",
    ):
        assert expected in output
    assert "technical_cause" not in output
    assert "BaseException" not in output
    assert "PostgreSQL" not in output


@pytest.mark.parametrize(
    "factory_error",
    (OperationalRuntimeUnavailableError("unavailable"),),
)
def test_runtime_unavailable_senza_fallback(factory_error) -> None:
    code, output, error, calls, target = execute(factory_error=factory_error)

    assert code == OperationalExitCode.OPERATION_RUNTIME_UNAVAILABLE == 3
    assert output == ""
    assert error == "OPERATION_RUNTIME_UNAVAILABLE\n"
    assert calls == ["settings.yaml"]
    assert target.calls == []


def test_entrypoint_assente_senza_fallback_o_retry() -> None:
    code, _, error, calls, target = execute(entry_point=False)

    assert code == 3
    assert error == "OPERATION_RUNTIME_UNAVAILABLE\n"
    assert calls == ["settings.yaml"]
    assert target is None


def test_unexpected_application_error_generico_senza_retry_o_causa() -> None:
    calls = []

    class RaisingEntryPoint:
        def execute(self, intent):
            calls.append(intent)
            try:
                raise RuntimeError("provider-cause-sensitive")
            except RuntimeError as cause:
                raise RuntimeError("provider-sensitive-detail") from cause

    def factory(settings_path):
        return SimpleNamespace(
            operational_scheduling_entry_point=RaisingEntryPoint()
        )

    stdout = StringIO()
    stderr = StringIO()
    code = run_operational_scheduling_command(
        args(),
        stdout=stdout,
        stderr=stderr,
        dependencies=OperationalCliDependencies(application_factory=factory),
    )

    assert code == OperationalExitCode.OPERATION_INTERNAL_ERROR == 5
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "OPERATION_INTERNAL_ERROR\n"
    assert "provider-sensitive-detail" not in stderr.getvalue()
    assert "provider-cause-sensitive" not in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()
    assert len(calls) == 1


def test_adapter_non_importa_boundary_vietati() -> None:
    source = Path("src/tpo_core/cli/operational.py").read_text(encoding="utf-8")
    for forbidden in (
        "CommitExecutionContext",
        "ActorId",
        "CommitOutcomeUncertain",
        "OperationalSchedulingOrchestrator",
        "ApplicationCommitter",
        "CommitRepository",
        "PostgreSQLCommitRepository",
        "GoogleSheetsCommitRepository",
    ):
        assert forbidden not in source
