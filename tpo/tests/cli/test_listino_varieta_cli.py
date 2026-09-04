from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.listino_varieta.errors import ListinoVarietaVarietaNotFoundError
from src.tpo_core.application.listino_varieta.models import ImpostaPrezzoListinoVarietaResult
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.listino_varieta import run_listino_varieta_command


def args(*extra):
    return [
        "listino-varieta", "set", "--varieta", "VAR-000001",
        "--prezzo-unitario", "12.50", "--aliquota-igic", "7", "--actor", "owner",
        "--reason", "Aggiornamento listino", "--correlation-id", "corr-listino-1", *extra,
    ]


def test_parser_registers_frozen_listino_varieta_command(monkeypatch):
    received = []
    monkeypatch.setattr(main_module, "run_listino_varieta_command", lambda a, **k: received.append(a) or 0)
    assert main_module.main(args()) == 0
    assert received[0].listino_varieta_command == "set"
    assert received[0].varieta == "VAR-000001"
    assert received[0].reason == "Aggiornamento listino"
    assert received[0].correlation_id == "corr-listino-1"


def test_missing_required_input_fails_before_runtime(monkeypatch):
    monkeypatch.setattr(main_module, "run_listino_varieta_command", lambda *a, **k: 99)
    assert main_module.main(["listino-varieta", "set"]) == 2


def test_cli_happy_path_is_thin(monkeypatch):
    class Writer:
        def imposta_prezzo(self, command):
            self.command = command
            return ImpostaPrezzoListinoVarietaResult(
                varieta_public_id=command.varieta_id.value,
                prezzo_unitario=command.prezzo_unitario,
                aliquota_igic=command.aliquota_igic,
                recorded_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
                inserted=True,
            )
    writer = Writer()
    import src.tpo_core.cli.listino_varieta as module
    monkeypatch.setattr(module, "build_listino_varieta_writer", lambda settings: writer)
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_listino_varieta_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert "VARIETA: VAR-000001" in stdout.getvalue()
    assert "PREZZO_UNITARIO: 12.50" in stdout.getvalue()
    assert stderr.getvalue() == ""
    assert writer.command.prezzo_unitario == Decimal("12.50")
    assert writer.command.authority.reason == "Aggiornamento listino"
    assert writer.command.authority.correlation_id == "corr-listino-1"


def test_cli_invalid_input_returns_input_exit(monkeypatch):
    parser = main_module._parser(); argv = args()
    argv[argv.index("--prezzo-unitario") + 1] = "not-a-decimal"
    namespace = parser.parse_args(argv); stdout, stderr = StringIO(), StringIO()
    assert run_listino_varieta_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "LISTINO_VARIETA_SET_FAILED" in stderr.getvalue()


def test_cli_invalid_varieta_identifier_returns_input_exit(monkeypatch):
    parser = main_module._parser(); argv = args()
    argv[argv.index("--varieta") + 1] = "not-a-varieta-id"
    namespace = parser.parse_args(argv); stdout, stderr = StringIO(), StringIO()
    assert run_listino_varieta_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "LISTINO_VARIETA_SET_FAILED" in stderr.getvalue()


def test_cli_blank_reason_returns_input_exit(monkeypatch):
    parser = main_module._parser(); argv = args()
    argv[argv.index("--reason") + 1] = "  "
    namespace = parser.parse_args(argv); stdout, stderr = StringIO(), StringIO()
    assert run_listino_varieta_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "LISTINO_VARIETA_SET_FAILED" in stderr.getvalue()


def test_cli_missing_varieta_returns_input_exit(monkeypatch):
    class Writer:
        def imposta_prezzo(self, command):
            raise ListinoVarietaVarietaNotFoundError("VARIETA assente.")
    import src.tpo_core.cli.listino_varieta as module
    monkeypatch.setattr(module, "build_listino_varieta_writer", lambda settings: Writer())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_listino_varieta_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "VARIETA assente." in stderr.getvalue()
