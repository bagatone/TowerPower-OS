from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.uscita.errors import UscitaOriginalIsCorrectionError
from src.tpo_core.application.uscita.models import (
    CorreggiUscitaResult, RegistraUscitaResult,
)
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.uscita import run_uscita_command
from src.tpo_core.domain.identifiers import UscitaId
from src.tpo_core.domain.states import CategoriaUscita, MetodoPagamento


def args(*extra):
    return ["uscita", "registra", "--importo", "45.50", "--data", "2026-09-04",
            "--categoria", "SEMENTI", "--beneficiario", "Vivai Canarias SL",
            "--metodo", "BONIFICO", "--actor", "owner", "--reason", "expense paid",
            "--correlation-id", "corr", "--idempotency-key", "idem", *extra]


def test_parser_registers_explicit_uscita_command():
    namespace = main_module._parser().parse_args(args())
    assert namespace.uscita_command == "registra"
    assert namespace.categoria == "SEMENTI"
    assert namespace.beneficiario == "Vivai Canarias SL"


def test_cli_is_thin_and_exposes_frozen_result(monkeypatch):
    class Service:
        def record(self, command):
            assert command.importo == Decimal("45.50")
            assert command.categoria == CategoriaUscita.SEMENTI
            return RegistraUscitaResult(
                UscitaId("USC-000001"), command.importo, command.data_uscita,
                command.categoria, command.beneficiario, command.metodo,
                datetime(2026, 9, 4, 8, 1, tzinfo=timezone.utc), "INSERTED",
            )
    import src.tpo_core.cli.uscita as module
    monkeypatch.setattr(module, "build_uscita_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_uscita_command(namespace, stdout=stdout, stderr=stderr) == 0
    output = stdout.getvalue()
    for value in (
        "USCITA_ID=USC-000001", "IMPORTO=45.50", "DATA_USCITA=2026-09-04",
        "CATEGORIA=SEMENTI", "BENEFICIARIO=Vivai Canarias SL", "METODO=BONIFICO",
        "OUTCOME=INSERTED",
    ):
        assert value in output
    assert stderr.getvalue() == ""


def correggi_args(*extra):
    return ["uscita", "correggi", "--originale", "USC-000001",
            "--importo", "-20.00", "--data", "2026-09-04", "--categoria", "SEMENTI",
            "--beneficiario", "Vivai Canarias SL", "--metodo", "BONIFICO",
            "--actor", "owner", "--reason", "correction", "--correlation-id", "corr",
            "--idempotency-key", "idem", *extra]


def test_parser_registers_explicit_uscita_correggi_command():
    namespace = main_module._parser().parse_args(correggi_args())
    assert namespace.uscita_command == "correggi"
    assert namespace.originale == "USC-000001"
    assert namespace.importo == "-20.00"


def test_correggi_cli_is_thin_and_exposes_frozen_result(monkeypatch):
    class Service:
        def correct(self, command):
            assert command.original_uscita_id == UscitaId("USC-000001")
            assert command.importo == Decimal("-20.00")
            return CorreggiUscitaResult(
                UscitaId("USC-000002"), command.original_uscita_id, command.importo,
                command.data_uscita, command.categoria, command.beneficiario,
                command.metodo, datetime(2026, 9, 4, 8, 2, tzinfo=timezone.utc), "INSERTED",
            )
    import src.tpo_core.cli.uscita as module
    monkeypatch.setattr(module, "build_uscita_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(correggi_args())
    stdout, stderr = StringIO(), StringIO()
    assert run_uscita_command(namespace, stdout=stdout, stderr=stderr) == 0
    output = stdout.getvalue()
    for value in (
        "USCITA_ID=USC-000002", "ORIGINAL_USCITA_ID=USC-000001", "IMPORTO=-20.00",
        "DATA_USCITA=2026-09-04", "CATEGORIA=SEMENTI",
        "BENEFICIARIO=Vivai Canarias SL", "METODO=BONIFICO", "OUTCOME=INSERTED",
    ):
        assert value in output
    assert stderr.getvalue() == ""


def test_correggi_cli_reports_typed_errors_without_traceback(monkeypatch):
    class Service:
        def correct(self, command):
            raise UscitaOriginalIsCorrectionError("Rettifica-di-rettifica non ammessa.")
    import src.tpo_core.cli.uscita as module
    monkeypatch.setattr(module, "build_uscita_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(correggi_args())
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_uscita_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 1
    assert "USCITA_ORIGINAL_IS_CORRECTION" in stderr.getvalue()
    assert stdout.getvalue() == ""


def test_blank_beneficiario_is_rejected_by_domain(monkeypatch):
    class Service:
        def record(self, command):
            raise AssertionError("non deve essere raggiunto")
    import src.tpo_core.cli.uscita as module
    monkeypatch.setattr(module, "build_uscita_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(
        ["uscita", "registra", "--importo", "10", "--data", "2026-09-04",
         "--categoria", "SEMENTI", "--beneficiario", "   ", "--metodo", "BONIFICO",
         "--actor", "owner", "--reason", "r", "--correlation-id", "c",
         "--idempotency-key", "i"]
    )
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_uscita_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 2
    assert "USCITA_INPUT_INVALID" in stderr.getvalue()


def test_invalid_categoria_choice_is_rejected_by_parser():
    try:
        main_module._parser().parse_args(
            ["uscita", "registra", "--importo", "1", "--data", "2026-09-04",
             "--categoria", "FORNITORI", "--beneficiario", "x", "--metodo", "BONIFICO",
             "--actor", "owner", "--reason", "r", "--correlation-id", "c",
             "--idempotency-key", "i"]
        )
        raised = False
    except main_module._UsageError:
        raised = True
    assert raised
