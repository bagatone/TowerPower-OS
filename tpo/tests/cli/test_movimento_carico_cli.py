from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.movimento_carico.errors import (
    MovimentoCaricoRaccoltaNotFoundError,
    MovimentoCaricoReconciliationRequiredError,
)
from src.tpo_core.application.movimento_carico.models import RegistraCaricoMagazzinoResult
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.movimento_carico import run_movimento_command
from src.tpo_core.domain.identifiers import MovimentoId, RaccoltaId, VarietaId
from src.tpo_core.domain.quantities import UnitOfMeasure


def args(*extra):
    return ["movimento", "carica-raccolta", "--raccolta", "RAC-000001",
            "--quantita-pesata", "450.5",
            "--effective-at", "2026-09-05T08:00:00+01:00",
            "--motivo", "pesatura carico magazzino",
            "--actor", "magazziniere", "--reason", "peso reale",
            "--correlation-id", "corr", "--idempotency-key", "idem",
            "--confirm", *extra]


def set_args(*extra):
    return ["movimento", "carica-raccolta", "--raccolta", "RAC-000001",
            "--unita-misura", "SET",
            "--effective-at", "2026-09-05T08:00:00+01:00",
            "--motivo", "carico SET da raccolta",
            "--actor", "magazziniere", "--reason", "raccolta reale",
            "--correlation-id", "corr-set", "--idempotency-key", "idem-set",
            "--confirm", *extra]


def test_parser_registers_explicit_movimento_command():
    namespace = main_module._parser().parse_args(args())
    assert namespace.movimento_command == "carica-raccolta" and namespace.confirm
    assert namespace.raccolta == "RAC-000001"
    assert namespace.quantita_pesata == "450.5"
    assert namespace.unita_misura == "GRAM"


def test_parser_accepts_set_unita_misura_without_quantita_pesata():
    namespace = main_module._parser().parse_args(set_args())
    assert namespace.unita_misura == "SET"
    assert namespace.quantita_pesata is None


def test_cli_is_thin_and_exposes_frozen_result(monkeypatch):
    class Service:
        def registra(self, command):
            assert command.raccolta_id == RaccoltaId("RAC-000001")
            assert command.unita_misura is UnitOfMeasure.GRAM
            assert command.quantita_pesata == Decimal("450.5")
            assert command.motivo == "pesatura carico magazzino"
            return RegistraCaricoMagazzinoResult(
                MovimentoId("MOV-000001"), RaccoltaId("RAC-000001"), VarietaId("VAR-000001"),
                command.unita_misura, command.quantita_pesata, command.effective_at,
                datetime(2026, 9, 5, 7, 1, tzinfo=timezone.utc),
                Decimal("450.5"), "INSERTED",
            )

    import src.tpo_core.cli.movimento_carico as module
    monkeypatch.setattr(module, "build_movimento_carico_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_movimento_command(namespace, stdout=stdout, stderr=stderr) == 0
    output = stdout.getvalue()
    for value in (
        "MOVIMENTO_ID=MOV-000001", "RACCOLTA_ID=RAC-000001", "VARIETA_ID=VAR-000001",
        "QUANTITA=450.5", "UOM=GRAM", "STOCK_DISPONIBILE=450.5", "OUTCOME=INSERTED",
    ):
        assert value in output
    assert stderr.getvalue() == ""


def test_cli_set_path_is_thin_and_exposes_frozen_result(monkeypatch):
    class Service:
        def registra(self, command):
            assert command.raccolta_id == RaccoltaId("RAC-000001")
            assert command.unita_misura is UnitOfMeasure.SET
            assert command.quantita_pesata is None
            return RegistraCaricoMagazzinoResult(
                MovimentoId("MOV-000002"), RaccoltaId("RAC-000001"), VarietaId("VAR-000001"),
                UnitOfMeasure.SET, Decimal("2"), command.effective_at,
                datetime(2026, 9, 5, 7, 1, tzinfo=timezone.utc),
                Decimal("2"), "INSERTED",
            )

    import src.tpo_core.cli.movimento_carico as module
    monkeypatch.setattr(module, "build_movimento_carico_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(set_args())
    stdout, stderr = StringIO(), StringIO()
    assert run_movimento_command(namespace, stdout=stdout, stderr=stderr) == 0
    output = stdout.getvalue()
    for value in (
        "MOVIMENTO_ID=MOV-000002", "RACCOLTA_ID=RAC-000001", "VARIETA_ID=VAR-000001",
        "QUANTITA=2", "UOM=SET", "STOCK_DISPONIBILE=2", "OUTCOME=INSERTED",
    ):
        assert value in output
    assert stderr.getvalue() == ""


def test_cli_set_path_rejects_quantita_pesata():
    namespace = main_module._parser().parse_args(set_args("--quantita-pesata", "1"))
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_movimento_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 2
    assert "MOVIMENTO_CARICO_INPUT_INVALID" in stderr.getvalue()
    assert stdout.getvalue() == ""


def test_cli_gram_path_requires_quantita_pesata():
    namespace = main_module._parser().parse_args(args())
    namespace.quantita_pesata = None
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_movimento_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 2
    assert "MOVIMENTO_CARICO_INPUT_INVALID" in stderr.getvalue()


def test_cli_reports_typed_errors_without_traceback(monkeypatch):
    class Service:
        def registra(self, command):
            raise MovimentoCaricoRaccoltaNotFoundError("RACCOLTA inesistente.")

    import src.tpo_core.cli.movimento_carico as module
    monkeypatch.setattr(module, "build_movimento_carico_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_movimento_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 1
    assert "MOVIMENTO_CARICO_RACCOLTA_NOT_FOUND" in stderr.getvalue()
    assert stdout.getvalue() == ""


def test_cli_reports_reconciliation_required_exit_code(monkeypatch):
    class Service:
        def registra(self, command):
            raise MovimentoCaricoReconciliationRequiredError("da riconciliare.")

    import src.tpo_core.cli.movimento_carico as module
    monkeypatch.setattr(module, "build_movimento_carico_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_movimento_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 4
    assert "MOVIMENTO_CARICO_RECONCILIATION_REQUIRED" in stderr.getvalue()


def test_cli_invalid_quantita_returns_input_exit():
    namespace = main_module._parser().parse_args(args())
    namespace.quantita_pesata = "not-a-number"
    stdout, stderr = StringIO(), StringIO()
    assert run_movimento_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "MOVIMENTO_CARICO_INPUT_INVALID" in stderr.getvalue()


def test_cli_invalid_effective_at_returns_input_exit():
    namespace = main_module._parser().parse_args(args())
    namespace.effective_at = "not-a-date"
    stdout, stderr = StringIO(), StringIO()
    assert run_movimento_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "MOVIMENTO_CARICO_INPUT_INVALID" in stderr.getvalue()
