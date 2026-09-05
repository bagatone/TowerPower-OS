from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.fattura_rettifica.errors import (
    FatturaRettificaReconciliationRequiredError,
)
from src.tpo_core.application.fattura_rettifica.models import RectifyFatturaResult
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.fattura import run_fattura_command
from src.tpo_core.domain.identifiers import ClienteId, NumeroFattura


def args(*extra):
    return [
        "fattura", "rettifica", "--rettifica-di", "2026/0001",
        "--riga", "1:-2.5", "--data-emissione", "2026-09-05", "--actor", "owner",
        "--reason", "errore quantità", "--correlation-id", "corr-1",
        "--idempotency-key", "key-1", "--confirm", *extra,
    ]


def test_parser_registers_rettifica_fattura_command(monkeypatch):
    received = []
    monkeypatch.setattr(main_module, "run_fattura_command", lambda a, **k: received.append(a) or 0)
    assert main_module.main(args()) == 0
    assert received[0].fattura_command == "rettifica"
    assert received[0].rettifica_di == "2026/0001"
    assert received[0].riga == ["1:-2.5"]
    assert received[0].confirm is True


def test_missing_required_input_fails_before_runtime(monkeypatch):
    monkeypatch.setattr(main_module, "run_fattura_command", lambda *a, **k: 99)
    assert main_module.main(["fattura", "rettifica"]) == 2


def test_cli_happy_path_is_thin(monkeypatch):
    class Service:
        def rectify(self, command):
            return RectifyFatturaResult(
                2, "INSERTED", NumeroFattura("2026/0002"), command.rettifica_di,
                ClienteId("CLI-000001"), command.data_emissione, date(2026, 10, 5),
                Decimal("-2.50"), Decimal("-0.18"), Decimal("-2.68"),
                len(command.righe), datetime.now(timezone.utc),
            )
    import src.tpo_core.cli.fattura as module
    monkeypatch.setattr(module, "build_fattura_rettifica_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_fattura_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert "NUMERO_FATTURA: 2026/0002" in stdout.getvalue()
    assert "RETTIFICA_DI: 2026/0001" in stdout.getvalue()
    assert "TOTALE: -2.68" in stdout.getvalue()
    assert "RIGHE: 1" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_cli_multi_riga_parsing(monkeypatch):
    class Service:
        def rectify(self, command):
            assert len(command.righe) == 2
            assert command.righe[0].posizione_originale == 1
            assert command.righe[0].quantita == Decimal("-2.5")
            assert command.righe[1].posizione_originale == 3
            assert command.righe[1].quantita == Decimal("1")
            return RectifyFatturaResult(
                2, "INSERTED", NumeroFattura("2026/0002"), command.rettifica_di,
                ClienteId("CLI-000001"), command.data_emissione, date(2026, 10, 5),
                Decimal("0.00"), Decimal("0.00"), Decimal("0.00"),
                len(command.righe), datetime.now(timezone.utc),
            )
    import src.tpo_core.cli.fattura as module
    monkeypatch.setattr(module, "build_fattura_rettifica_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser()
    namespace = parser.parse_args(args("--riga", "3:1"))
    stdout, stderr = StringIO(), StringIO()
    assert run_fattura_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert stderr.getvalue() == ""


def test_cli_invalid_riga_format_returns_input_exit(monkeypatch):
    parser = main_module._parser(); argv = args()
    argv[argv.index("--riga") + 1] = "not-a-riga"
    namespace = parser.parse_args(argv); stdout, stderr = StringIO(), StringIO()
    assert run_fattura_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "FATTURA_RETTIFICA_INPUT_INVALID" in stderr.getvalue()


def test_cli_invalid_input_returns_input_exit(monkeypatch):
    parser = main_module._parser(); argv = args()
    argv[argv.index("--data-emissione") + 1] = "not-a-date"
    namespace = parser.parse_args(argv); stdout, stderr = StringIO(), StringIO()
    assert run_fattura_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "FATTURA_RETTIFICA_INPUT_INVALID" in stderr.getvalue()


def test_cli_reconciliation_required_maps_to_reconciliation_exit(monkeypatch):
    class Service:
        def rectify(self, command):
            raise FatturaRettificaReconciliationRequiredError("esito incerto")
    import src.tpo_core.cli.fattura as module
    monkeypatch.setattr(module, "build_fattura_rettifica_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_fattura_command(namespace, stdout=stdout, stderr=stderr) == 4
    assert "FATTURA_RETTIFICA_RECONCILIATION_REQUIRED" in stderr.getvalue()
