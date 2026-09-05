from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.assegnazione_fisica.errors import (
    AssegnazioneFisicaRaccoltaNotFoundError,
    AssegnazioneFisicaReconciliationRequiredError,
)
from src.tpo_core.application.assegnazione_fisica.models import RegistraAssegnazioneFisicaResult
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.assegnazione_fisica import run_assegnazione_fisica_command
from src.tpo_core.domain.identifiers import (
    AssegnazioneFisicaId, ConsegnaId, RaccoltaId, RigaOrdineId,
)


def args(*extra):
    return ["assegnazione", "registra", "--raccolta", "RAC-000001",
            "--riga-ordine", "RO-000001",
            "--quantita", "120.5", "--unita-misura", "GRAM",
            "--effective-at", "2026-09-05T08:00:00+01:00",
            "--motivo", "assegnazione raccolta a riga ordine",
            "--actor", "operatore", "--reason", "assegnazione fisica",
            "--correlation-id", "corr", "--idempotency-key", "idem",
            "--confirm", *extra]


def test_parser_registers_explicit_assegnazione_command():
    namespace = main_module._parser().parse_args(args())
    assert namespace.assegnazione_command == "registra" and namespace.confirm
    assert namespace.raccolta == "RAC-000001"
    assert namespace.riga_ordine == "RO-000001"
    assert namespace.consegna is None


def test_parser_accepts_optional_consegna():
    namespace = main_module._parser().parse_args(args("--consegna", "CON-000001"))
    assert namespace.consegna == "CON-000001"


def test_cli_is_thin_and_exposes_frozen_result(monkeypatch):
    class Service:
        def registra(self, command):
            assert command.raccolta_id == RaccoltaId("RAC-000001")
            assert command.riga_ordine_id == RigaOrdineId("RO-000001")
            assert command.quantita_assegnata == Decimal("120.5")
            assert command.motivo == "assegnazione raccolta a riga ordine"
            assert command.consegna_id is None
            return RegistraAssegnazioneFisicaResult(
                AssegnazioneFisicaId("ASF-000001"), RaccoltaId("RAC-000001"),
                RigaOrdineId("RO-000001"), command.quantita_assegnata,
                command.unita_misura, command.effective_at,
                datetime(2026, 9, 5, 7, 1, tzinfo=timezone.utc), "INSERTED",
            )

    import src.tpo_core.cli.assegnazione_fisica as module
    monkeypatch.setattr(module, "build_assegnazione_fisica_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_assegnazione_fisica_command(namespace, stdout=stdout, stderr=stderr) == 0
    output = stdout.getvalue()
    for value in (
        "ASSEGNAZIONE_FISICA_ID=ASF-000001", "RACCOLTA_ID=RAC-000001",
        "RIGA_ORDINE_ID=RO-000001", "CONSEGNA_ID=", "QUANTITA_ASSEGNATA=120.5",
        "UOM=GRAM", "OUTCOME=INSERTED",
    ):
        assert value in output
    assert stderr.getvalue() == ""


def test_cli_forwards_consegna_id_when_provided(monkeypatch):
    class Service:
        def registra(self, command):
            assert command.consegna_id == ConsegnaId("CON-000001")
            return RegistraAssegnazioneFisicaResult(
                AssegnazioneFisicaId("ASF-000001"), RaccoltaId("RAC-000001"),
                RigaOrdineId("RO-000001"), command.quantita_assegnata,
                command.unita_misura, command.effective_at,
                datetime(2026, 9, 5, 7, 1, tzinfo=timezone.utc), "INSERTED",
                consegna_id=ConsegnaId("CON-000001"),
            )

    import src.tpo_core.cli.assegnazione_fisica as module
    monkeypatch.setattr(module, "build_assegnazione_fisica_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args("--consegna", "CON-000001"))
    stdout, stderr = StringIO(), StringIO()
    assert run_assegnazione_fisica_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert "CONSEGNA_ID=CON-000001" in stdout.getvalue()


def test_cli_reports_typed_errors_without_traceback(monkeypatch):
    class Service:
        def registra(self, command):
            raise AssegnazioneFisicaRaccoltaNotFoundError("RACCOLTA inesistente.")

    import src.tpo_core.cli.assegnazione_fisica as module
    monkeypatch.setattr(module, "build_assegnazione_fisica_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_assegnazione_fisica_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 1
    assert "ASSEGNAZIONE_FISICA_RACCOLTA_NOT_FOUND" in stderr.getvalue()
    assert stdout.getvalue() == ""


def test_cli_reports_reconciliation_required_exit_code(monkeypatch):
    class Service:
        def registra(self, command):
            raise AssegnazioneFisicaReconciliationRequiredError("da riconciliare.")

    import src.tpo_core.cli.assegnazione_fisica as module
    monkeypatch.setattr(module, "build_assegnazione_fisica_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_assegnazione_fisica_command(namespace, stdout=stdout, stderr=stderr)
    assert exit_code == 4
    assert "ASSEGNAZIONE_FISICA_RECONCILIATION_REQUIRED" in stderr.getvalue()


def test_cli_invalid_quantita_returns_input_exit():
    namespace = main_module._parser().parse_args(args())
    namespace.quantita = "not-a-number"
    stdout, stderr = StringIO(), StringIO()
    assert run_assegnazione_fisica_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "ASSEGNAZIONE_FISICA_INPUT_INVALID" in stderr.getvalue()


def test_cli_invalid_effective_at_returns_input_exit():
    namespace = main_module._parser().parse_args(args())
    namespace.effective_at = "not-a-date"
    stdout, stderr = StringIO(), StringIO()
    assert run_assegnazione_fisica_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "ASSEGNAZIONE_FISICA_INPUT_INVALID" in stderr.getvalue()
