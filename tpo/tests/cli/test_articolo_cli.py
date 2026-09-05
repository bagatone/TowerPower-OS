from datetime import datetime, timezone
from io import StringIO

from src.tpo_core.application.articolo.errors import (
    ArticoloReconciliationRequiredError,
    InvalidArticoloCommandError,
)
from src.tpo_core.application.articolo.models import CommissionArticoloResult
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.articolo import run_articolo_command
from src.tpo_core.domain.identifiers import ArticoloId


def args(*extra):
    return ["articolo", "commissiona",
            "--denominazione", "Substrato fibra di cocco",
            "--unita-misura", "GRAM",
            "--actor", "magazziniere", "--reason", "nuovo materiale",
            "--correlation-id", "corr", "--idempotency-key", "idem",
            "--confirm", *extra]


def test_parser_registers_explicit_articolo_command():
    namespace = main_module._parser().parse_args(args())
    assert namespace.articolo_command == "commissiona" and namespace.confirm
    assert namespace.denominazione == "Substrato fibra di cocco"
    assert namespace.unita_misura == "GRAM"


def test_cli_is_thin_and_exposes_frozen_result(monkeypatch):
    class Service:
        def commission(self, command):
            assert command.denominazione == "Substrato fibra di cocco"
            assert command.unita_misura == "GRAM"
            return CommissionArticoloResult(
                ArticoloId("ART-000001"), command.denominazione, command.unita_misura,
                datetime(2026, 9, 5, 7, 1, tzinfo=timezone.utc), "INSERTED",
            )

    import src.tpo_core.cli.articolo as module
    monkeypatch.setattr(module, "build_articolo_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_articolo_command(namespace, stdout=stdout, stderr=stderr) == 0
    output = stdout.getvalue()
    for value in (
        "ARTICOLO_ID=ART-000001", "DENOMINAZIONE=Substrato fibra di cocco",
        "UOM=GRAM", "OUTCOME=INSERTED",
    ):
        assert value in output
    assert stderr.getvalue() == ""


def test_cli_reports_reconciliation_required_exit_code(monkeypatch):
    class Service:
        def commission(self, command):
            raise ArticoloReconciliationRequiredError("da riconciliare.")

    import src.tpo_core.cli.articolo as module
    monkeypatch.setattr(module, "build_articolo_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_articolo_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 4
    assert "ARTICOLO_RECONCILIATION_REQUIRED" in stderr.getvalue()


def test_cli_invalid_denominazione_returns_input_exit():
    namespace = main_module._parser().parse_args(args())
    namespace.denominazione = "   "
    stdout, stderr = StringIO(), StringIO()
    assert run_articolo_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "ARTICOLO_INPUT_INVALID" in stderr.getvalue()
