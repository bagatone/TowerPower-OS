from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.fattura_emissione.errors import FatturaReconciliationRequiredError
from src.tpo_core.application.fattura_emissione.models import EmitFatturaResult
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.fattura import run_fattura_command
from src.tpo_core.domain.identifiers import NumeroFattura


def args(*extra):
    return [
        "fattura", "emetti", "--client", "CLI-000001",
        "--consegna", "CON-000001", "--consegna", "CON-000002",
        "--data-emissione", "2026-09-03", "--actor", "owner", "--reason", "emissione",
        "--correlation-id", "corr-1", "--idempotency-key", "key-1", "--confirm", *extra,
    ]


def test_parser_registers_frozen_fattura_command(monkeypatch):
    received = []
    monkeypatch.setattr(main_module, "run_fattura_command", lambda a, **k: received.append(a) or 0)
    assert main_module.main(args()) == 0
    assert received[0].fattura_command == "emetti"
    assert received[0].consegna == ["CON-000001", "CON-000002"]
    assert received[0].confirm is True


def test_missing_required_input_fails_before_runtime(monkeypatch):
    monkeypatch.setattr(main_module, "run_fattura_command", lambda *a, **k: 99)
    assert main_module.main(["fattura", "emetti"]) == 2


def test_cli_happy_path_is_thin(monkeypatch):
    class Service:
        def emit(self, command):
            return EmitFatturaResult(
                1, "INSERTED", NumeroFattura("2026/0001"), command.cliente_id,
                command.data_emissione, date(2026, 10, 3), Decimal("100.00"),
                Decimal("7.00"), Decimal("107.00"), len(command.consegna_ids), 2,
                datetime.now(timezone.utc),
            )
    import src.tpo_core.cli.fattura as module
    monkeypatch.setattr(module, "build_fattura_emissione_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_fattura_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert "NUMERO_FATTURA: 2026/0001" in stdout.getvalue()
    assert "TOTALE: 107.00" in stdout.getvalue()
    assert "CONSEGNE: 2" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_cli_invalid_input_returns_input_exit(monkeypatch):
    parser = main_module._parser(); argv = args()
    argv[argv.index("--data-emissione") + 1] = "not-a-date"
    namespace = parser.parse_args(argv); stdout, stderr = StringIO(), StringIO()
    assert run_fattura_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "FATTURA_EMISSIONE_INPUT_INVALID" in stderr.getvalue()


def test_cli_reconciliation_required_maps_to_reconciliation_exit(monkeypatch):
    class Service:
        def emit(self, command):
            raise FatturaReconciliationRequiredError("esito incerto")
    import src.tpo_core.cli.fattura as module
    monkeypatch.setattr(module, "build_fattura_emissione_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_fattura_command(namespace, stdout=stdout, stderr=stderr) == 4
    assert "FATTURA_EMISSIONE_RECONCILIATION_REQUIRED" in stderr.getvalue()
