from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
import json

from src.tpo_core.application.semina_commissioning.models import CommissionSeminaResult
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.semina import run_semina_command
from src.tpo_core.domain.identifiers import LottoSemeId, SeminaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.traceability import SeminaTraceabilityCode


def args(*extra):
    facts = {key: "OWNER_AUTHORIZED" for key in (
        "physical_started_at", "actual_seed_grams", "selected_lse", "selected_pv", "origin",
    )}
    return ["semina", "commission", "--seed-lot", "LSE-000001",
            "--expected-seed-lot-version", "0", "--protocol-version", "PV-000001",
            "--actual-seed-grams", "1.25", "--physical-started-at", "2026-08-25T08:00:00+01:00",
            "--origin", "ORDINE_CLIENTE", "--provenance", json.dumps(facts),
            "--actor", "owner", "--reason", "start", "--correlation-id", "corr",
            "--idempotency-key", "idem", "--confirm", *extra]


def test_parser_registers_semina_and_rejects_unfrozen_origin():
    namespace = main_module._parser().parse_args(args())
    assert namespace.semina_command == "commission" and namespace.confirm
    invalid = args(); invalid[invalid.index("--origin") + 1] = "TEST"
    assert main_module.main(invalid) == 2


def test_independent_happy_path_is_thin(monkeypatch):
    class Service:
        def commission(self, command):
            assert command.planning_start is None
            return CommissionSeminaResult(
                SeminaId("SEM-000001"), SeminaTraceabilityCode("AFI-2508-A"),
                "INSERTED", "AVVIATA", LottoSemeId("LSE-000001"),
                1, Quantity(Decimal("8.75"), UnitOfMeasure.GRAM), None, None,
                datetime.now(timezone.utc),
            )
    import src.tpo_core.cli.semina as module
    monkeypatch.setattr(module, "build_semina_commissioning_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_semina_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert "PUBLIC_ID: SEM-000001" in stdout.getvalue() and stderr.getvalue() == ""


def test_partial_planning_arguments_fail_before_runtime():
    namespace = main_module._parser().parse_args(args("--planning-line", "RPS-000001"))
    stdout, stderr = StringIO(), StringIO()
    assert run_semina_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "SEMINA_INPUT_INVALID" in stderr.getvalue()
