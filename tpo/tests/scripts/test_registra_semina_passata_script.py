import importlib.util
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "commissioning" / "2026-10-06_registra_semina_passata.py"


def load():
    spec = importlib.util.spec_from_file_location("registra_semina_passata", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self.sql = ""
        self.params = ()

    def execute(self, sql, params=()):
        self.sql, self.params = sql, params

    def fetchall(self):
        return [self.state["semina"]] if "FROM tpo.semine" in self.sql and self.state.get("semina") else []

    def fetchone(self):
        if "protocollo_versioni" in self.sql:
            return (Decimal("1"), "SET", 11, 10, 0)
        return None


class FakeConn:
    def __init__(self, state):
        self.cursor_ = FakeCursor(state)
        self.commits = 0
        self.closed = False

    def cursor(self):
        return self.cursor_

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def patch(monkeypatch, module, state, calls, predictive_calls):
    monkeypatch.setattr(module.base, "resolve_protocol", lambda cur, nome: ("PV-1", Decimal("12")))
    monkeypatch.setattr(module.base, "resolve_seed_lot", lambda cur, nome, g: ("LSE-1", 3))

    def fake_run(cmd, capture_output, text):
        calls.append(cmd)
        if cmd[1:3] == ["semina", "commission"]:
            state["semina"] = ("SEM-000030", "HIN-2909-A", "AVVIATA", 1, False)

        class Done:
            returncode, stdout, stderr = 0, "ok", ""
        return Done()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.authority, "commission_predictive",
                        lambda cur, **kw: (predictive_calls.append(kw) or (tuple(kw["declared_sets"]), ())))


def test_preview_writes_nothing(monkeypatch):
    module = load()
    state, calls, pcalls = {}, [], []
    patch(monkeypatch, module, state, calls, pcalls)
    module.run(FakeConn(state), lambda: FakeConn(state), False, "Hinojo", 1, date(2026, 9, 29), "09:00")
    assert calls == [] and pcalls == []


def test_execute_commissions_then_germination_then_predictive_and_no_materials(monkeypatch):
    module = load()
    state, calls, pcalls = {}, [], []
    patch(monkeypatch, module, state, calls, pcalls)
    pconn = FakeConn(state)
    semina, codice = module.run(FakeConn(state), lambda: pconn, True, "Hinojo", 1, date(2026, 9, 29), "09:00")
    assert semina == "SEM-000030"
    assert [tuple(c[1:3]) for c in calls] == [("semina", "commission"), ("semina", "transition")]   # niente materiali
    first = calls[0]
    assert first[first.index("--actual-seed-grams") + 1] == "12"
    assert first[first.index("--physical-started-at") + 1] == "2026-09-29T09:00:00+01:00"
    assert "stimata" in first[first.index("--reason") + 1]
    trans = calls[1]
    assert trans[trans.index("--target-state") + 1] == "GERMINAZIONE"
    assert trans[trans.index("--effective-at") + 1] == "2026-09-29T09:00:00+01:00"
    assert pcalls[0]["declared_sets"] == {"SEM-000030": 1} and pconn.commits == 1 and pconn.closed


def test_rerun_on_germination_with_predictive_done_does_nothing(monkeypatch):
    module = load()
    state, calls, pcalls = {"semina": ("SEM-000030", "HIN-2909-A", "GERMINAZIONE", 2, True)}, [], []
    patch(monkeypatch, module, state, calls, pcalls)
    module.run(FakeConn(state), lambda: FakeConn(state), True, "Hinojo", 1, date(2026, 9, 29), "09:00")
    assert calls == [] and pcalls == []
