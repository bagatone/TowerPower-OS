from io import StringIO

from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.listino_varieta import run_listino_varieta_command
from src.tpo_core.infrastructure.postgresql.fatturazione_configuration import (
    ListinoVarietaValidationError,
)


def args(*extra):
    return [
        "listino-varieta", "set", "--varieta", "VAR-000001",
        "--prezzo-unitario", "12.50", "--aliquota-igic", "7", "--actor", "owner", *extra,
    ]


def test_parser_registers_frozen_listino_varieta_command(monkeypatch):
    received = []
    monkeypatch.setattr(main_module, "run_listino_varieta_command", lambda a, **k: received.append(a) or 0)
    assert main_module.main(args()) == 0
    assert received[0].listino_varieta_command == "set"
    assert received[0].varieta == "VAR-000001"


def test_missing_required_input_fails_before_runtime(monkeypatch):
    monkeypatch.setattr(main_module, "run_listino_varieta_command", lambda *a, **k: 99)
    assert main_module.main(["listino-varieta", "set"]) == 2


def test_cli_happy_path_is_thin(monkeypatch):
    class Writer:
        def set_prezzo(self, **kwargs):
            self.kwargs = kwargs
    writer = Writer()
    import src.tpo_core.cli.listino_varieta as module
    monkeypatch.setattr(module, "build_listino_varieta_writer", lambda settings: writer)
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_listino_varieta_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert "VARIETA: VAR-000001" in stdout.getvalue()
    assert "PREZZO_UNITARIO: 12.50" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_cli_invalid_input_returns_input_exit(monkeypatch):
    parser = main_module._parser(); argv = args()
    argv[argv.index("--prezzo-unitario") + 1] = "not-a-decimal"
    namespace = parser.parse_args(argv); stdout, stderr = StringIO(), StringIO()
    assert run_listino_varieta_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "LISTINO_VARIETA_SET_FAILED" in stderr.getvalue()


def test_cli_missing_varieta_returns_input_exit(monkeypatch):
    class Writer:
        def set_prezzo(self, **kwargs):
            raise ListinoVarietaValidationError("VARIETA assente.")
    import src.tpo_core.cli.listino_varieta as module
    monkeypatch.setattr(module, "build_listino_varieta_writer", lambda settings: Writer())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_listino_varieta_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "VARIETA assente." in stderr.getvalue()
