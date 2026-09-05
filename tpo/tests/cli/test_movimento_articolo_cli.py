from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.movimento_articolo.errors import (
    MovimentoArticoloArticoloNotFoundError,
    MovimentoArticoloReconciliationRequiredError,
)
from src.tpo_core.application.movimento_articolo.models import (
    RegistraMovimentoArticoloResult,
)
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.movimento_articolo import run_movimento_articolo_command
from src.tpo_core.domain.identifiers import ArticoloId, MovimentoId


def args(command_name="carica-articolo", *extra):
    base = ["movimento", command_name, "--articolo", "ART-000001",
            "--quantita", "25.5", "--unita-misura", "GRAM",
            "--effective-at", "2026-09-05T08:00:00+01:00",
            "--motivo", "rifornimento substrato",
            "--actor", "magazziniere", "--reason", "rifornimento",
            "--correlation-id", "corr", "--idempotency-key", "idem",
            "--confirm"]
    if command_name == "rettifica-articolo":
        base = base[:2] + ["--direzione", "NEGATIVO"] + base[2:]
    return base + list(extra)


def test_parser_registers_explicit_movimento_command():
    namespace = main_module._parser().parse_args(args())
    assert namespace.movimento_command == "carica-articolo" and namespace.confirm
    assert namespace.articolo == "ART-000001"
    assert namespace.quantita == "25.5"


def test_parser_requires_direzione_for_rettifica():
    namespace = main_module._parser().parse_args(args("rettifica-articolo"))
    assert namespace.movimento_command == "rettifica-articolo"
    assert namespace.direzione == "NEGATIVO"


def test_cli_is_thin_and_exposes_frozen_result(monkeypatch):
    class Service:
        def registra(self, command):
            assert command.articolo_id == ArticoloId("ART-000001")
            assert command.quantita == Decimal("25.5")
            return RegistraMovimentoArticoloResult(
                MovimentoId("MOV-000001"), ArticoloId("ART-000001"), command.quantita,
                command.unita_misura, command.effective_at,
                datetime(2026, 9, 5, 7, 1, tzinfo=timezone.utc), Decimal("25.5"), "INSERTED",
            )

    import src.tpo_core.cli.movimento_articolo as module
    monkeypatch.setattr(module, "build_movimento_articolo_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_movimento_articolo_command(namespace, stdout=stdout, stderr=stderr) == 0
    output = stdout.getvalue()
    for value in (
        "MOVIMENTO_ID=MOV-000001", "ARTICOLO_ID=ART-000001", "QUANTITA=25.5",
        "UOM=GRAM", "STOCK_DISPONIBILE=25.5", "OUTCOME=INSERTED",
    ):
        assert value in output
    assert stderr.getvalue() == ""


def test_cli_reports_typed_errors_without_traceback(monkeypatch):
    class Service:
        def registra(self, command):
            raise MovimentoArticoloArticoloNotFoundError("ARTICOLO inesistente.")

    import src.tpo_core.cli.movimento_articolo as module
    monkeypatch.setattr(module, "build_movimento_articolo_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_movimento_articolo_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 1
    assert "MOVIMENTO_ARTICOLO_ARTICOLO_NOT_FOUND" in stderr.getvalue()
    assert stdout.getvalue() == ""


def test_cli_reports_reconciliation_required_exit_code(monkeypatch):
    class Service:
        def registra(self, command):
            raise MovimentoArticoloReconciliationRequiredError("da riconciliare.")

    import src.tpo_core.cli.movimento_articolo as module
    monkeypatch.setattr(module, "build_movimento_articolo_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_movimento_articolo_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 4
    assert "MOVIMENTO_ARTICOLO_RECONCILIATION_REQUIRED" in stderr.getvalue()


def test_cli_invalid_quantita_returns_input_exit():
    namespace = main_module._parser().parse_args(args())
    namespace.quantita = "not-a-number"
    stdout, stderr = StringIO(), StringIO()
    assert run_movimento_articolo_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "MOVIMENTO_ARTICOLO_INPUT_INVALID" in stderr.getvalue()


def test_cli_invalid_effective_at_returns_input_exit():
    namespace = main_module._parser().parse_args(args())
    namespace.effective_at = "not-a-date"
    stdout, stderr = StringIO(), StringIO()
    assert run_movimento_articolo_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "MOVIMENTO_ARTICOLO_INPUT_INVALID" in stderr.getvalue()


def test_rettifica_without_direzione_returns_input_exit():
    namespace = main_module._parser().parse_args(args("carica-articolo"))
    namespace.movimento_command = "rettifica-articolo"
    namespace.direzione = None
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_movimento_articolo_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 2
    assert "MOVIMENTO_ARTICOLO_INPUT_INVALID" in stderr.getvalue()
