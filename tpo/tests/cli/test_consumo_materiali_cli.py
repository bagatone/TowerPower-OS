from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.consumo_materiali import (
    ConsumoMaterialiArticoloNotFoundError, RegistraConsumoMaterialiSeminaResult,
)
from src.tpo_core.application.movimento_articolo.errors import (
    MovimentoArticoloInsufficientStockError,
)
from src.tpo_core.application.movimento_articolo.models import RegistraMovimentoArticoloResult
from src.tpo_core.cli import main as main_module
import src.tpo_core.cli.consumo_materiali as module
from src.tpo_core.domain.identifiers import ArticoloId, MovimentoId, SeminaId

NOW = datetime(2026, 10, 4, 11, tzinfo=timezone.utc)


def args(*extra):
    return ["materiali", "consumo-semina", "--semina", "SEM-000021", "--set", "7",
            "--actor", "matteo", "--reason", "consumo", "--correlation-id", "corr",
            "--confirm", *extra]


def _result(art, n):
    return RegistraMovimentoArticoloResult(
        MovimentoId(f"MOV-00000{n}"), ArticoloId(art), Decimal("28"), "UNIT", NOW, NOW,
        Decimal("2972"), "INSERTED")


def run(monkeypatch, service):
    monkeypatch.setattr(module, "build_consumo_materiali_service", lambda settings: service)
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    out, err = StringIO(), StringIO()
    return module.run_consumo_materiali_command(namespace, stdout=out, stderr=err), out, err


def test_parser_defaults_to_four_pieces_per_set():
    namespace = main_module._parser().parse_args(args())
    assert namespace.set_seminati == 7 and namespace.pezzi_per_set == 4 and namespace.confirm


def test_cli_prints_both_movements(monkeypatch):
    class Service:
        def registra(self, command):
            assert command.set_seminati == 7 and command.pezzi == 28
            return RegistraConsumoMaterialiSeminaResult(
                command.semina_id, "AFI-0410-A", 7, 4, _result("ART-000002", 1), _result("ART-000001", 2))
    code, out, err = run(monkeypatch, Service())
    assert code == 0 and err.getvalue() == ""
    for value in ("SEMINA_ID=SEM-000021", "CODICE_TRACCIABILITA=AFI-0410-A", "SET=7",
                  "VASCHETTE_QUANTITA=28", "SUBSTRATO_OUTCOME=INSERTED"):
        assert value in out.getvalue()


def test_cli_reports_typed_errors(monkeypatch):
    class Missing:
        def registra(self, command):
            raise ConsumoMaterialiArticoloNotFoundError("manca")
    code, _, err = run(monkeypatch, Missing())
    assert code == 1 and "CONSUMO_MATERIALI_ARTICOLO_NOT_FOUND" in err.getvalue()

    class Short:
        def registra(self, command):
            raise MovimentoArticoloInsufficientStockError("giacenza")
    code, _, err = run(monkeypatch, Short())
    assert code == 1 and "INSUFFICIENT_STOCK" in err.getvalue()
