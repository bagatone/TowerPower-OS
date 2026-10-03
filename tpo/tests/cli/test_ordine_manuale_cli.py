from datetime import date
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.ordine_manuale import (
    OrdineManualeClienteNotFoundError,
    RegistraOrdineManualeResult,
    RigaOrdineRegistrata,
)
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.ordine_manuale import run_ordine_command
from src.tpo_core.domain.identifiers import ClienteId, OrdineId, RigaOrdineId, VarietaId
from src.tpo_core.domain.quantities import UnitOfMeasure

ARGS = [
    "ordine", "registra-manuale", "--client", "CLI-000012", "--data-ordine", "2026-10-03",
    "--data-consegna-prevista", "2026-10-05", "--riga", "VAR-000001:1:SET",
    "--riga", "VAR-000002:1.5:SET", "--actor", "owner", "--reason", "ordine extra",
    "--correlation-id", "corr-1", "--idempotency-key", "key-1", "--confirm",
]


def _patch(monkeypatch, service):
    import src.tpo_core.cli.ordine_manuale as module
    monkeypatch.setattr(module, "build_ordine_manuale_service", lambda settings: service)
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())


def test_cli_ordine_manuale_parses_lines_and_prints_versions(monkeypatch):
    captured = {}

    class Service:
        def registra(self, command):
            captured["command"] = command
            return RegistraOrdineManualeResult(
                OrdineId("ORD-000050"), ClienteId("CLI-000012"), "APERTO", 0,
                (RigaOrdineRegistrata(RigaOrdineId("RO-000200"), 1, VarietaId("VAR-000001"),
                                      Decimal("1"), UnitOfMeasure.SET),),
                "INSERTED",
            )
    _patch(monkeypatch, Service())
    namespace = main_module._parser().parse_args(ARGS)
    stdout, stderr = StringIO(), StringIO()
    assert run_ordine_command(namespace, stdout=stdout, stderr=stderr) == 0
    command = captured["command"]
    assert command.data_consegna_prevista == date(2026, 10, 5)
    assert [(r.varieta_id.value, r.quantita) for r in command.righe] == [
        ("VAR-000001", Decimal("1")), ("VAR-000002", Decimal("1.5")),
    ]
    assert "ORDINE_ID=ORD-000050" in stdout.getvalue()
    assert "RIGA=RO-000200 POS=1" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_cli_ordine_manuale_reports_failures(monkeypatch):
    class Service:
        def registra(self, command):
            raise OrdineManualeClienteNotFoundError("CLIENTE inesistente.")
    _patch(monkeypatch, Service())
    stdout, stderr = StringIO(), StringIO()
    namespace = main_module._parser().parse_args(ARGS)
    assert run_ordine_command(namespace, stdout=stdout, stderr=stderr) != 0
    assert "ORDINE_MANUALE_CLIENTE_NOT_FOUND" in stderr.getvalue()
    bad = main_module._parser().parse_args(ARGS[:9] + ["VAR-000001-1-SET"] + ARGS[10:])
    stderr = StringIO()
    assert run_ordine_command(bad, stdout=StringIO(), stderr=stderr) != 0
    assert "INPUT_INVALID" in stderr.getvalue()
