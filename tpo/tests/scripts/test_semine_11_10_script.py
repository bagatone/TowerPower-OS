"""Semine dell'11/10/2026: voci dichiarate, nessuna semina nel futuro, comando correttivo."""
import importlib.util
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "commissioning" / "2026-10-11_semine.py"
TZ = timezone(timedelta(hours=1))


def _module():
    spec = importlib.util.spec_from_file_location("semine_11_10", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeMattina:
    def __init__(self):
        self.SEMINE, self.calls = [], []

    def run(self, conn, esegui, ora, giorno):
        self.calls.append((self.SEMINE[0], ora, giorno, esegui))
        nome, n = self.SEMINE[0]
        return [(nome, n, f"SEM-9{len(self.calls):05d}", f"TST-{len(self.calls):04d}-A")]


def test_declared_entries_and_afila_only_when_given_and_after_21():
    module = _module()
    assert module.elenco(None) == [("Rabano", 3, date(2026, 10, 10), "21:00"),
                                   ("Cilantro", 7, date(2026, 10, 11), "09:00")]
    assert module.elenco(5)[-1] == ("Afila", 5, date(2026, 10, 11), "21:00")
    mattina = datetime(2026, 10, 11, 12, 0, tzinfo=TZ)
    sera = datetime(2026, 10, 11, 21, 5, tzinfo=TZ)
    assert module.controlla_passato(module.elenco(None), mattina) is None
    assert "futuro" in module.controlla_passato(module.elenco(5), mattina)
    assert module.controlla_passato(module.elenco(5), sera) is None
    # prima del 21:00 del 10/10 la semina di Rabano non sarebbe registrabile
    assert module.controlla_passato(module.elenco(None), datetime(2026, 10, 10, 20, 0, tzinfo=TZ))


def test_run_writes_each_declared_sowing_with_its_own_time_and_prints_corrective(capsys):
    module, fake = _module(), FakeMattina()
    adesso = datetime(2026, 10, 11, 12, 0, tzinfo=TZ)
    assert module.run(FakeConn(["Rabano", "Cilantro"]), True, None, adesso, fake) == 0
    assert [(c[0], c[1], c[2]) for c in fake.calls] == [
        (("Rabano", 3), "21:00", date(2026, 10, 10)), (("Cilantro", 7), "09:00", date(2026, 10, 11))]
    out = capsys.readouterr().out
    assert "--semina SEM-900001 --esito interruzione --venduti 0 --scartati 0 --esegui" in out
    assert "--semina SEM-900002" in out


def test_run_refuses_future_and_writes_nothing(capsys):
    module, fake = _module(), FakeMattina()
    adesso = datetime(2026, 10, 11, 12, 0, tzinfo=TZ)
    assert module.run(FakeConn(["Rabano", "Cilantro", "Afila"]), True, 4, adesso, fake) == 1
    assert fake.calls == []
    assert "futuro" in capsys.readouterr().err


class FakeConn:
    def __init__(self, nomi): self.nomi = nomi
    def cursor(self): return self
    def execute(self, sql): pass
    def fetchall(self): return [(n,) for n in self.nomi]


def test_variety_names_resolve_to_the_exact_system_denomination():
    import pytest
    module = _module()
    conn = FakeConn(["Afila", "Cilantro", "Rábano Morado", "Mizuna Roja"])
    assert module.risolvi_varieta(conn, "Rabano") == "Rábano Morado"
    assert module.risolvi_varieta(conn, "cilantro") == "Cilantro"
    with pytest.raises(SystemExit):
        module.risolvi_varieta(conn, "Pak Choi")
    with pytest.raises(SystemExit):
        module.risolvi_varieta(FakeConn(["Rábano Morado", "Rábano Blanco"]), "Rabano")


def test_run_uses_resolved_names(capsys):
    module, fake = _module(), FakeMattina()
    conn = FakeConn(["Cilantro", "Rábano Morado"])
    assert module.run(conn, True, None, datetime(2026, 10, 11, 12, 0, tzinfo=TZ), fake) == 0
    assert [c[0][0] for c in fake.calls] == ["Rábano Morado", "Cilantro"]
