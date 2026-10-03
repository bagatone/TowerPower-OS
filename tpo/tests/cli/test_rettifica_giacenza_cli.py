from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.rettifica_giacenza import (
    RettificaGiacenzaResult,
    RettificaGiacenzaStockError,
)
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.rettifica_giacenza import run_rettifica_giacenza_command
from src.tpo_core.domain.identifiers import MovimentoId, VarietaId
from src.tpo_core.domain.quantities import UnitOfMeasure

ARGS = [
    "movimento", "rettifica-giacenza", "--varieta", "VAR-000001", "--unita-misura", "SET",
    "--quantita", "2", "--effective-at", "2026-10-03T08:00:00+01:00",
    "--motivo", "vendita non registrata", "--actor", "owner", "--reason", "pulizia giacenza",
    "--correlation-id", "corr-1", "--idempotency-key", "key-1", "--confirm",
]


def _patch(monkeypatch, service):
    import src.tpo_core.cli.rettifica_giacenza as module
    monkeypatch.setattr(module, "build_rettifica_giacenza_service", lambda settings: service)
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())


def test_cli_rettifica_giacenza_commits_and_prints_result(monkeypatch):
    captured = {}

    class Service:
        def registra(self, command):
            captured["command"] = command
            now = datetime(2026, 10, 3, 8, tzinfo=timezone.utc)
            return RettificaGiacenzaResult(
                MovimentoId("MOV-000050"), VarietaId("VAR-000001"), UnitOfMeasure.SET,
                Decimal("2"), now, now, Decimal("0"), "INSERTED",
            )
    _patch(monkeypatch, Service())
    namespace = main_module._parser().parse_args(ARGS + ["--semina", "SEM-000002"])
    stdout, stderr = StringIO(), StringIO()
    assert run_rettifica_giacenza_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert captured["command"].origin_semina.value == "SEM-000002"
    assert "MOVIMENTO_ID=MOV-000050" in stdout.getvalue()
    assert "STOCK_DISPONIBILE=0" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_cli_rettifica_giacenza_reports_domain_failure_and_invalid_input(monkeypatch):
    class Service:
        def registra(self, command):
            raise RettificaGiacenzaStockError("STOCK insufficiente")
    _patch(monkeypatch, Service())
    stdout, stderr = StringIO(), StringIO()
    namespace = main_module._parser().parse_args(ARGS)
    assert run_rettifica_giacenza_command(namespace, stdout=stdout, stderr=stderr) != 0
    assert "RETTIFICA_GIACENZA_STOCK_INSUFFICIENT" in stderr.getvalue()
    bad = main_module._parser().parse_args(ARGS[:7] + ["abc"] + ARGS[8:])
    stderr = StringIO()
    assert run_rettifica_giacenza_command(bad, stdout=StringIO(), stderr=stderr) != 0 and "INPUT_INVALID" in stderr.getvalue()
