from io import StringIO

from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.cliente import run_cliente_command
from src.tpo_core.infrastructure.postgresql.fatturazione_configuration import (
    ClienteFatturazioneValidationError,
)


def args(*extra):
    return [
        "cliente", "fatturazione", "--client", "CLI-000001",
        "--modalita-fatturazione", "PERIODICA_MENSILE", "--termini-pagamento-giorni", "30",
        "--actor", "owner", *extra,
    ]


def test_parser_registers_frozen_cliente_command(monkeypatch):
    received = []
    monkeypatch.setattr(main_module, "run_cliente_command", lambda a, **k: received.append(a) or 0)
    assert main_module.main(args()) == 0
    assert received[0].cliente_command == "fatturazione"
    assert received[0].modalita_fatturazione == "PERIODICA_MENSILE"
    assert received[0].termini_pagamento_giorni == 30


def test_missing_required_input_fails_before_runtime(monkeypatch):
    monkeypatch.setattr(main_module, "run_cliente_command", lambda *a, **k: 99)
    assert main_module.main(["cliente", "fatturazione"]) == 2


def test_invalid_modalita_is_rejected_by_the_parser(monkeypatch):
    monkeypatch.setattr(main_module, "run_cliente_command", lambda *a, **k: 99)
    argv = args(); argv[argv.index("--modalita-fatturazione") + 1] = "MENSILE"
    assert main_module.main(argv) == 2


def test_cli_happy_path_is_thin(monkeypatch):
    class Writer:
        def set_fatturazione(self, **kwargs):
            self.kwargs = kwargs
    writer = Writer()
    import src.tpo_core.cli.cliente as module
    monkeypatch.setattr(module, "build_cliente_fatturazione_writer", lambda settings: writer)
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_cliente_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert "MODALITA_FATTURAZIONE: PERIODICA_MENSILE" in stdout.getvalue()
    assert "TERMINI_PAGAMENTO_GIORNI: 30" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_cli_non_positive_termini_returns_input_exit(monkeypatch):
    parser = main_module._parser(); argv = args()
    argv[argv.index("--termini-pagamento-giorni") + 1] = "0"
    namespace = parser.parse_args(argv); stdout, stderr = StringIO(), StringIO()
    assert run_cliente_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "CLIENTE_FATTURAZIONE_SET_FAILED" in stderr.getvalue()


def test_cli_missing_cliente_returns_input_exit(monkeypatch):
    class Writer:
        def set_fatturazione(self, **kwargs):
            raise ClienteFatturazioneValidationError("CLIENTE assente.")
    import src.tpo_core.cli.cliente as module
    monkeypatch.setattr(module, "build_cliente_fatturazione_writer", lambda settings: Writer())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_cliente_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "CLIENTE assente." in stderr.getvalue()
