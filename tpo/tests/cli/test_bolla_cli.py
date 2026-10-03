from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO

import pytest

from src.tpo_core.application.bolla_lettura import (
    Bolla, ConsegnaNonConsegnataError, ConsegnaNonTrovataError, OrigineLotto, RigaBolla,
)
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.bolla import _slug, run_bolla_command
from src.tpo_core.domain.identifiers import ConsegnaId

pytest.importorskip("reportlab")

NOW = datetime(2099, 1, 1, 10, tzinfo=timezone.utc)


def _bolla() -> Bolla:
    return Bolla(
        ConsegnaId("CON-000012"), "CONSEGNATA", "CLI-000003", "Azul y Sal Ñ",
        date(2099, 1, 1), NOW, None, None,
        (RigaBolla(1, "ORD-000001", "VAR-000001", "Rábano", Decimal("2"), "SET", False,
                   (OrigineLotto("RAB-0210-A", "RAC-000001", NOW, Decimal("2")),),
                   Decimal("0")),),
    )


def _patch(monkeypatch, service):
    import src.tpo_core.cli.bolla as module
    monkeypatch.setattr(module, "build_bolla_lettura_service", lambda settings: service)
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())


def _run(*extra):
    namespace = main_module._parser().parse_args(["bolla", "genera", *extra])
    stdout, stderr = StringIO(), StringIO()
    code = run_bolla_command(namespace, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


class _Service:
    def __init__(self, result=None, error=None):
        self._result, self._error = result, error

    def bolla(self, query):
        if self._error:
            raise self._error
        return self._result


def test_genera_writes_pdf_in_output_dir(monkeypatch, tmp_path):
    _patch(monkeypatch, _Service(_bolla()))
    code, out, err = _run("--consegna", "CON-000012", "--output-dir", str(tmp_path))
    assert code == 0, err
    files = list(tmp_path.glob("*.pdf"))
    assert [f.name for f in files] == ["bolla_CON-000012_azul-y-sal-n_2099-01-01.pdf"]
    assert files[0].read_bytes().startswith(b"%PDF-")
    assert "STATUS: GENERATED" in out and "RIGHE_CON_QUANTITA_SENZA_ORIGINE: 0" in out


def test_genera_refuses_to_overwrite_without_flag(monkeypatch, tmp_path):
    _patch(monkeypatch, _Service(_bolla()))
    assert _run("--consegna", "CON-000012", "--output-dir", str(tmp_path))[0] == 0
    code, out, err = _run("--consegna", "CON-000012", "--output-dir", str(tmp_path))
    assert code == 1 and "BOLLA_FILE_ESISTENTE" in err and out == ""
    assert _run("--consegna", "CON-000012", "--output-dir", str(tmp_path),
                "--sovrascrivi")[0] == 0


def test_genera_reports_not_found_and_not_delivered(monkeypatch, tmp_path):
    _patch(monkeypatch, _Service(error=ConsegnaNonTrovataError("assente")))
    code, _, err = _run("--consegna", "CON-000099", "--output-dir", str(tmp_path))
    assert code == 1 and "BOLLA_CONSEGNA_NON_TROVATA" in err
    _patch(monkeypatch, _Service(error=ConsegnaNonConsegnataError("no")))
    code, _, err = _run("--consegna", "CON-000012", "--output-dir", str(tmp_path))
    assert code == 1 and "BOLLA_CONSEGNA_NON_CONSEGNATA" in err
    assert list(tmp_path.iterdir()) == []


def test_genera_rejects_malformed_consegna_id(monkeypatch, tmp_path):
    _patch(monkeypatch, _Service(_bolla()))
    code, _, err = _run("--consegna", "XYZ", "--output-dir", str(tmp_path))
    assert code == 2 and "BOLLA_INPUT_INVALID" in err


def test_emittente_file_is_loaded_and_validated(monkeypatch, tmp_path):
    _patch(monkeypatch, _Service(_bolla()))
    good = tmp_path / "emittente.yaml"
    good.write_text('righe:\n  - "Tower Power (prova)"\n', encoding="utf-8")
    assert _run("--consegna", "CON-000012", "--output-dir", str(tmp_path / "o"),
                "--emittente-file", str(good))[0] == 0
    bad = tmp_path / "bad.yaml"
    bad.write_text("altro: 1\n", encoding="utf-8")
    code, _, err = _run("--consegna", "CON-000012", "--output-dir", str(tmp_path / "o2"),
                        "--emittente-file", str(bad))
    assert code == 2 and "righe" in err
    code, _, err = _run("--consegna", "CON-000012", "--emittente-file",
                        str(tmp_path / "manca.yaml"))
    assert code == 2


def test_slug_is_ascii_and_never_empty():
    assert _slug("Azul y Sal Ñ") == "azul-y-sal-n"
    assert _slug("???") == "cliente"
