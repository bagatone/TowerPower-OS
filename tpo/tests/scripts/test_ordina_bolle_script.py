"""Riordino delle bolle PDF in sottocartelle per cliente: anteprima, spostamento, nessuna sovrascrittura."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "commissioning" / "2026-10-09_ordina_bolle.py"


def _module():
    spec = importlib.util.spec_from_file_location("ordina_bolle", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make(folder: Path) -> None:
    for name in ("bolla_CON-000008_splash_2026-10-09.pdf", "bolla_CON-000009_azul-y-sal_2026-10-09.pdf",
                 "bolla_CON-000011_alchimia-sushi_2026-10-09.pdf", "note.pdf", "appunti.txt"):
        (folder / name).write_bytes(name.encode())


def test_preview_moves_nothing_and_execute_sorts_by_customer(tmp_path):
    module, lines = _module(), []
    _make(tmp_path)
    assert module.run(tmp_path, False, out=lines.append) == 0
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == sorted(
        ["bolla_CON-000008_splash_2026-10-09.pdf", "bolla_CON-000009_azul-y-sal_2026-10-09.pdf",
         "bolla_CON-000011_alchimia-sushi_2026-10-09.pdf", "note.pdf", "appunti.txt"])
    assert not any(p.is_dir() for p in tmp_path.iterdir()) and "Da spostare: 3" in "\n".join(lines)

    assert module.run(tmp_path, True, out=lines.append) == 0
    assert (tmp_path / "splash" / "bolla_CON-000008_splash_2026-10-09.pdf").read_bytes().startswith(b"bolla_CON-000008")
    assert (tmp_path / "azul-y-sal" / "bolla_CON-000009_azul-y-sal_2026-10-09.pdf").exists()
    assert (tmp_path / "alchimia-sushi" / "bolla_CON-000011_alchimia-sushi_2026-10-09.pdf").exists()
    assert (tmp_path / "note.pdf").exists() and (tmp_path / "appunti.txt").exists()      # non sono bolle: restano

    lines.clear()                                                                          # rilancio: niente da fare
    assert module.run(tmp_path, True, out=lines.append) == 0 and "Spostate: 0" in "\n".join(lines)


def test_never_overwrites_and_rejects_missing_folder(tmp_path):
    module, lines = _module(), []
    (tmp_path / "splash").mkdir()
    (tmp_path / "splash" / "bolla_CON-000008_splash_2026-10-09.pdf").write_bytes(b"gia' ordinata")
    (tmp_path / "bolla_CON-000008_splash_2026-10-09.pdf").write_bytes(b"duplicato")
    assert module.run(tmp_path, True, out=lines.append) == 0
    assert (tmp_path / "splash" / "bolla_CON-000008_splash_2026-10-09.pdf").read_bytes() == b"gia' ordinata"
    assert (tmp_path / "bolla_CON-000008_splash_2026-10-09.pdf").read_bytes() == b"duplicato"
    assert "SALTO" in "\n".join(lines)
    assert module.run(tmp_path / "non-esiste", True, out=lines.append) == 2
