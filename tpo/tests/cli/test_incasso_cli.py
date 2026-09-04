from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.incasso.errors import IncassoCorrectionFatturaMismatchError
from src.tpo_core.application.incasso.models import (
    CorreggiIncassoResult, RegistraIncassoResult,
)
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.incasso import run_incasso_command
from src.tpo_core.domain.identifiers import IncassoId, NumeroFattura
from src.tpo_core.domain.states import MetodoPagamento


def args(*extra):
    return ["incasso", "registra", "--fattura", "2026/0001",
            "--importo", "107.40", "--data", "2026-09-04", "--metodo", "BONIFICO",
            "--actor", "owner", "--reason", "payment received",
            "--correlation-id", "corr", "--idempotency-key", "idem", *extra]


def test_parser_registers_explicit_incasso_command():
    namespace = main_module._parser().parse_args(args())
    assert namespace.incasso_command == "registra"
    assert namespace.fattura == "2026/0001"


def test_cli_is_thin_and_exposes_frozen_result(monkeypatch):
    class Service:
        def record(self, command):
            assert command.fattura_numero == NumeroFattura("2026/0001")
            assert command.importo == Decimal("107.40")
            return RegistraIncassoResult(
                IncassoId("INC-000001"), command.fattura_numero, command.importo,
                command.data_incasso, command.metodo,
                datetime(2026, 9, 4, 8, 1, tzinfo=timezone.utc), "INSERTED",
            )
    import src.tpo_core.cli.incasso as module
    monkeypatch.setattr(module, "build_incasso_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_incasso_command(namespace, stdout=stdout, stderr=stderr) == 0
    output = stdout.getvalue()
    for value in (
        "INCASSO_ID=INC-000001", "FATTURA_NUMERO=2026/0001", "IMPORTO=107.40",
        "DATA_INCASSO=2026-09-04", "METODO=BONIFICO", "OUTCOME=INSERTED",
    ):
        assert value in output
    assert stderr.getvalue() == ""


def correggi_args(*extra):
    return ["incasso", "correggi", "--originale", "INC-000001",
            "--fattura", "2026/0001", "--importo", "-50.00", "--data", "2026-09-04",
            "--metodo", "BONIFICO", "--actor", "owner", "--reason", "correction",
            "--correlation-id", "corr", "--idempotency-key", "idem", *extra]


def test_parser_registers_explicit_incasso_correggi_command():
    namespace = main_module._parser().parse_args(correggi_args())
    assert namespace.incasso_command == "correggi"
    assert namespace.originale == "INC-000001"
    assert namespace.importo == "-50.00"


def test_correggi_cli_is_thin_and_exposes_frozen_result(monkeypatch):
    class Service:
        def correct(self, command):
            assert command.original_incasso_id == IncassoId("INC-000001")
            assert command.fattura_numero == NumeroFattura("2026/0001")
            assert command.importo == Decimal("-50.00")
            return CorreggiIncassoResult(
                IncassoId("INC-000002"), command.original_incasso_id, command.fattura_numero,
                command.importo, command.data_incasso, command.metodo,
                datetime(2026, 9, 4, 8, 2, tzinfo=timezone.utc), "INSERTED",
            )
    import src.tpo_core.cli.incasso as module
    monkeypatch.setattr(module, "build_incasso_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(correggi_args())
    stdout, stderr = StringIO(), StringIO()
    assert run_incasso_command(namespace, stdout=stdout, stderr=stderr) == 0
    output = stdout.getvalue()
    for value in (
        "INCASSO_ID=INC-000002", "ORIGINAL_INCASSO_ID=INC-000001",
        "FATTURA_NUMERO=2026/0001", "IMPORTO=-50.00", "DATA_INCASSO=2026-09-04",
        "METODO=BONIFICO", "OUTCOME=INSERTED",
    ):
        assert value in output
    assert stderr.getvalue() == ""


def test_correggi_cli_reports_typed_errors_without_traceback(monkeypatch):
    class Service:
        def correct(self, command):
            raise IncassoCorrectionFatturaMismatchError("FATTURA diversa dall'originale.")
    import src.tpo_core.cli.incasso as module
    monkeypatch.setattr(module, "build_incasso_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(correggi_args())
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_incasso_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 1
    assert "INCASSO_CORRECTION_FATTURA_MISMATCH" in stderr.getvalue()
    assert stdout.getvalue() == ""


def test_invalid_metodo_choice_is_rejected_by_parser():
    try:
        main_module._parser().parse_args(
            ["incasso", "registra", "--fattura", "2026/0001", "--importo", "1",
             "--data", "2026-09-04", "--metodo", "ASSEGNO", "--actor", "owner",
             "--reason", "r", "--correlation-id", "c", "--idempotency-key", "i"]
        )
        raised = False
    except main_module._UsageError:
        raised = True
    assert raised
