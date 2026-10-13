from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.pagamento_consegna.errors import (
    PagamentoConsegnaGiaPagataError, PagamentoConsegnaReconciliationRequiredError,
)
from src.tpo_core.application.pagamento_consegna.models import (
    AnnullaPagamentoConsegnaResult, RegistraPagamentoConsegnaResult,
)
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.pagamento_consegna import run_pagamento_consegna_command
from src.tpo_core.domain.identifiers import ConsegnaId, PagamentoConsegnaId

NOW = datetime(2026, 10, 11, 8, 1, tzinfo=timezone.utc)
COMMON = ["--actor", "owner", "--reason", "pagamento", "--correlation-id", "corr",
          "--idempotency-key", "idem"]


def registra(*extra):
    return ["pagamento-consegna", "registra", "--consegna", "CON-000008", "--data", "2026-10-09",
            "--metodo", "CONTANTI", *COMMON, *extra]


def _patch(monkeypatch, service):
    import src.tpo_core.cli.pagamento_consegna as module
    monkeypatch.setattr(module, "build_pagamento_consegna_service", lambda settings: service)
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())


def _run(argv):
    namespace = main_module._parser().parse_args(argv)
    stdout, stderr = StringIO(), StringIO()
    return run_pagamento_consegna_command(namespace, stdout=stdout, stderr=stderr), \
        stdout.getvalue(), stderr.getvalue()


def test_parser_amount_is_optional_and_storico_is_a_flag():
    namespace = main_module._parser().parse_args(registra())
    assert namespace.pagamento_consegna_command == "registra"
    assert namespace.importo is None and namespace.storico is False
    namespace = main_module._parser().parse_args(registra("--importo", "12.50", "--storico"))
    assert namespace.importo == "12.50" and namespace.storico is True


def test_registra_is_thin_and_prints_result(monkeypatch):
    class Service:
        def record(self, command):
            assert command.consegna_id == ConsegnaId("CON-000008")
            assert command.importo is None and command.storico is True
            return RegistraPagamentoConsegnaResult(
                PagamentoConsegnaId("PGC-000001"), command.consegna_id, command.data_pagamento,
                command.metodo, command.importo, command.storico, NOW, "INSERTED")
    _patch(monkeypatch, Service())
    code, out, err = _run(registra("--storico"))
    assert code == 0 and err == ""
    for value in ("PAGAMENTO_CONSEGNA_ID=PGC-000001", "CONSEGNA=CON-000008",
                  "DATA_PAGAMENTO=2026-10-09", "METODO=CONTANTI", "IMPORTO=", "STORICO=SI",
                  "OUTCOME=INSERTED"):
        assert value in out


def test_annulla_is_thin(monkeypatch):
    class Service:
        def cancel(self, command):
            assert command.pagamento_id == PagamentoConsegnaId("PGC-000001")
            return AnnullaPagamentoConsegnaResult(
                PagamentoConsegnaId("PGC-000002"), command.pagamento_id,
                ConsegnaId("CON-000008"), NOW, "INSERTED")
    _patch(monkeypatch, Service())
    code, out, _ = _run(["pagamento-consegna", "annulla", "--originale", "PGC-000001", *COMMON])
    assert code == 0 and "PAGAMENTO_CONSEGNA_ANNULLAMENTO_ID=PGC-000002" in out


def test_errors_map_to_exit_codes(monkeypatch):
    class Boom:
        def __init__(self, error): self.error = error
        def record(self, command): raise self.error
    _patch(monkeypatch, Boom(PagamentoConsegnaGiaPagataError("gia' pagata")))
    code, _, err = _run(registra())
    assert code != 0 and "PAGAMENTO_CONSEGNA_GIA_PAGATA" in err
    _patch(monkeypatch, Boom(PagamentoConsegnaReconciliationRequiredError("boh")))
    code, _, err = _run(registra())
    assert code != 0 and "RECONCILIATION" in err
    code, _, err = _run(registra("--importo", "-3"))
    assert code == 2 and "PAGAMENTO_CONSEGNA_IMPORTO_INVALIDO" in err
    code, _, err = _run(["pagamento-consegna", "registra", "--consegna", "XYZ", "--data",
                         "2026-10-09", "--metodo", "CONTANTI", *COMMON])
    assert code == 2
