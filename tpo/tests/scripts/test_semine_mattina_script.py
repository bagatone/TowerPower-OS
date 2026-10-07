import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "commissioning" / "2026-10-06_semine_mattina.py"


def load():
    spec = importlib.util.spec_from_file_location("semine_mattina", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    def __init__(self, started):
        self.started = started  # varieta' -> (SEM, codice) gia' presenti
        self.last = None

    def execute(self, sql, params=()):
        self.last = params


    def fetchall(self):
        nome = self.last[0]
        return [self.started[nome]] if nome in self.started else []


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor

    def cursor(self):
        return self._c


def patch(monkeypatch, module, cursor, calls):
    monkeypatch.setattr(module.base, "resolve_protocol", lambda cur, nome: (f"PV-{nome}", Decimal("10")))
    monkeypatch.setattr(module.base, "resolve_seed_lot", lambda cur, nome, g: (f"LSE-{nome}", 3))

    def fake_run(cmd, capture_output, text):
        calls.append(cmd)
        if cmd[1:3] == ["semina", "commission"]:
            nome = cmd[cmd.index("--correlation-id") + 1].rsplit("2026-10-06-", 1)[1]
            cursor.started[{"mizuna": "Mizuna", "rucola": "Rucola", "pak-choi": "Pak Choi"}[nome]] = (
                f"SEM-{len(cursor.started) + 100}", f"{nome[:3].upper()}-0610-A")

        class Done:
            returncode, stdout, stderr = 0, "ok", ""
        return Done()

    monkeypatch.setattr(module.subprocess, "run", fake_run)


def test_preview_writes_nothing(monkeypatch):
    module = load()
    calls = []
    cursor = FakeCursor({})
    patch(monkeypatch, module, cursor, calls)
    result = module.run(FakeConn(cursor), False, "09:00")
    assert calls == []
    assert [r[0] for r in result] == ["Mizuna", "Rucola", "Pak Choi"]


def test_execute_commissions_then_consumes_materials(monkeypatch):
    module = load()
    calls = []
    cursor = FakeCursor({})
    patch(monkeypatch, module, cursor, calls)
    result = module.run(FakeConn(cursor), True, "09:00")
    kinds = [tuple(c[1:3]) for c in calls]
    assert kinds == [("semina", "commission"), ("materiali", "consumo-semina")] * 3
    first = calls[0]
    assert first[first.index("--actual-seed-grams") + 1] == "10"
    assert first[first.index("--physical-started-at") + 1] == "2026-10-06T09:00:00+01:00"
    assert first[first.index("--origin") + 1] == "RIPRISTINO_STOCK"
    consumo = calls[1]
    assert consumo[consumo.index("--semina") + 1] == result[0][2] and "--set" in consumo
    assert all(r[2].startswith("SEM-") for r in result)


def test_rerun_skips_commission_but_keeps_idempotent_consumption(monkeypatch):
    module = load()
    calls = []
    cursor = FakeCursor({"Mizuna": ("SEM-000024", "MIZ-0610-A"), "Rucola": ("SEM-000025", "RUC-0610-A"),
                         "Pak Choi": ("SEM-000026", "PAK-0610-A")})
    patch(monkeypatch, module, cursor, calls)
    module.run(FakeConn(cursor), True, "09:00")
    assert [tuple(c[1:3]) for c in calls] == [("materiali", "consumo-semina")] * 3
