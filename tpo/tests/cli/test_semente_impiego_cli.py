from datetime import date, datetime, timezone
from io import StringIO

from src.tpo_core.application.semente_impiego_commissioning.models import (
    CommissionSementeImpiegoResult,
)
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.semente_impiego import run_semente_impiego_command
from src.tpo_core.domain.states import SementeRaccomandazione


def args(*extra):
    return [
        "semente-impiego", "commission", "--fornitore", "INTERSEMILLAS",
        "--referenza-commerciale", "VERDE MICROGREENS", "--protocol-version", "PV-000001",
        "--raccomandazione", "RACCOMANDATA", "--rating", "85",
        "--actor", "owner", "--reason", "commission", "--correlation-id", "corr-1",
        "--idempotency-key", "key-1", "--confirm", *extra,
    ]


def test_parser_registers_frozen_semente_impiego_command(monkeypatch):
    received = []
    monkeypatch.setattr(main_module, "run_semente_impiego_command", lambda a, **k: received.append(a) or 0)
    assert main_module.main(args()) == 0
    assert received[0].semente_impiego_command == "commission"
    assert received[0].raccomandazione == "RACCOMANDATA"
    assert received[0].confirm is True


def test_missing_required_input_fails_before_runtime(monkeypatch):
    monkeypatch.setattr(main_module, "run_semente_impiego_command", lambda *a, **k: 99)
    assert main_module.main(["semente-impiego", "commission"]) == 2


def test_cli_happy_path_is_thin(monkeypatch):
    class Service:
        def commission(self, command):
            return CommissionSementeImpiegoResult(
                1, "INSERTED", command.fornitore, command.referenza_commerciale,
                "VAR-000001", "Cilantro", "Microgreens", command.raccomandazione,
                command.rating, command.motivazione, date(2026, 9, 3), datetime.now(timezone.utc),
            )
    import src.tpo_core.cli.semente_impiego as module
    monkeypatch.setattr(module, "build_semente_impiego_commissioning_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_semente_impiego_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert "INTERNAL_ID: 1" in stdout.getvalue()
    assert "USE: VAR-000001 / Cilantro / Microgreens" in stdout.getvalue()
    assert "RACCOMANDAZIONE: RACCOMANDATA" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_cli_invalid_input_returns_input_exit(monkeypatch):
    parser = main_module._parser(); argv = args()
    argv[argv.index("--fornitore") + 1] = "  "
    namespace = parser.parse_args(argv); stdout, stderr = StringIO(), StringIO()
    assert run_semente_impiego_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "SEMENTE_IMPIEGO_INPUT_INVALID" in stderr.getvalue()
