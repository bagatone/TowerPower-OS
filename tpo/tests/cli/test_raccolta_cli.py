from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.raccolta.models import RecordRaccoltaResult
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.raccolta import run_raccolta_command
from src.tpo_core.domain.identifiers import RaccoltaId, SeminaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.traceability import SeminaTraceabilityCode


def args(*extra):
    return ["raccolta", "record", "--semina", "SEM-000001",
            "--quantity", "0.5", "--uom", "SET",
            "--effective-at", "2026-08-30T08:00:00+01:00",
            "--actor", "owner", "--reason", "physical harvest",
            "--correlation-id", "corr", "--idempotency-key", "idem",
            "--confirm", *extra]


def test_parser_registers_explicit_raccolta_command():
    namespace = main_module._parser().parse_args(args())
    assert namespace.raccolta_command == "record" and namespace.confirm


def test_cli_is_thin_and_exposes_frozen_result(monkeypatch):
    class Service:
        def record(self, command):
            assert command.semina_id == SeminaId("SEM-000001")
            assert command.quantity == Quantity(Decimal("0.5"), UnitOfMeasure.SET)
            return RecordRaccoltaResult(
                RaccoltaId("RAC-000001"), SeminaId("SEM-000001"),
                SeminaTraceabilityCode("CIL-3008-A"), command.quantity,
                command.effective_at, datetime(2026, 8, 30, 8, 1, tzinfo=timezone.utc),
                "INSERTED",
            )
    import src.tpo_core.cli.raccolta as module
    monkeypatch.setattr(module, "build_raccolta_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_raccolta_command(namespace, stdout=stdout, stderr=stderr) == 0
    output = stdout.getvalue()
    for value in (
        "RACCOLTA_ID=RAC-000001", "SEMINA_ID=SEM-000001",
        "TRACEABILITY_CODE=CIL-3008-A", "QUANTITY=0.5", "UOM=SET",
        "OUTCOME=INSERTED",
    ):
        assert value in output
    assert stderr.getvalue() == ""
