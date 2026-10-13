"""Semine del 12/10/2026: elenco dichiarato, nomi esatti, controllo preliminare prima di scrivere, nessun futuro."""
import importlib.util
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "commissioning" / "2026-10-12_semine.py"
TZ = timezone(timedelta(hours=1))
NOMI = ["Amaranto", "Hinojo", "Basilico", "Cavolo rosso", "Pak Choi", "Girasole", "Afila"]


def _module():
    spec = importlib.util.spec_from_file_location("semine_12_10", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeConn:
    def __init__(self, nomi): self.nomi = nomi
    def cursor(self): return self
    def execute(self, sql): pass
    def fetchall(self): return [(n,) for n in self.nomi]


class FakeMattina:
    def __init__(self, fail_on=None):
        self.SEMINE, self.calls, self.fail_on = [], [], fail_on

    def run(self, conn, esegui, ora, giorno):
        nome, n = self.SEMINE[0]
        self.calls.append((nome, n, ora, giorno, esegui))
        if esegui is False and nome in (self.fail_on or ()):
            raise SystemExit(f"manca il protocollo per {nome}")
        return [(nome, n, f"SEM-9{len(self.calls):05d}", f"TST-{len(self.calls):04d}-A")]


ADESSO = datetime(2026, 10, 12, 10, 0, tzinfo=TZ)


def test_default_list_is_six_single_sets_at_nine():
    module = _module()
    assert module.voci(None, "09:00") == [(n, 1, date(2026, 10, 12), "09:00") for n in
                                          ("Amaranto", "Hinojo", "Basilico", "Cavolo rosso", "Pak Choi", "Girasole")]
    assert module.voci(["Afila:2"], "08:30") == [("Afila", 2, date(2026, 10, 12), "08:30")]
    with pytest.raises(SystemExit):
        module.voci(["Afila:0"], "09:00")


def test_preview_writes_nothing_and_execute_checks_everything_before_writing(capsys):
    module = _module()
    fake = FakeMattina()
    assert module.run(FakeConn(NOMI), False, mattina=fake, adesso=ADESSO) == 0
    assert [c[4] for c in fake.calls] == [False] * 6
    capsys.readouterr()
    fake = FakeMattina()
    assert module.run(FakeConn(NOMI), True, mattina=fake, adesso=ADESSO) == 0
    assert [c[4] for c in fake.calls] == [False] * 6 + [True] * 6        # prima tutte in anteprima, poi la scrittura
    out = capsys.readouterr().out
    assert out.count("--esito interruzione") == 6 and "--semina SEM-900007" in out


def test_missing_protocols_are_all_listed_and_nothing_is_written(capsys):
    module = _module()
    fake = FakeMattina(fail_on=("Cavolo rosso", "Girasole"))
    assert module.run(FakeConn(NOMI), True, mattina=fake, adesso=ADESSO) == 1
    assert not any(c[4] for c in fake.calls)                            # nessuna scrittura
    assert [c[0] for c in fake.calls] == ["Amaranto", "Hinojo", "Basilico", "Cavolo rosso", "Pak Choi", "Girasole"]
    err = capsys.readouterr().err
    assert "- Cavolo rosso: manca il protocollo per Cavolo rosso" in err and "- Girasole: manca il protocollo per Girasole" in err
    assert "Cavolo rosso, Girasole" in err and "Nulla e' stato scritto" in err
    assert '--riga "Amaranto:1"' in err and '--riga "Pak Choi:1"' in err and '--riga "Girasole' not in err


def test_future_start_is_refused_and_unknown_variety_stops(capsys):
    module = _module()
    fake = FakeMattina()
    assert module.run(FakeConn(NOMI), True, mattina=fake, adesso=datetime(2026, 10, 12, 8, 0, tzinfo=TZ)) == 1
    assert fake.calls == [] and "futuro" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        module.run(FakeConn(["Amaranto"]), True, mattina=FakeMattina(), adesso=ADESSO)


def test_another_day_can_be_chosen_for_the_sowing(capsys):
    module = _module()
    assert module.voci(["Lenticchia:2"], "09:00", date(2026, 10, 13)) == [("Lenticchia", 2, date(2026, 10, 13), "09:00")]
    fake = FakeMattina()
    adesso = datetime(2026, 10, 13, 10, 0, tzinfo=TZ)
    assert module.run(FakeConn(NOMI + ["Lenticchia"]), False, ["Lenticchia:2"], mattina=fake, adesso=adesso,
                      giorno=date(2026, 10, 13)) == 0
    assert fake.calls == [("Lenticchia", 2, "09:00", date(2026, 10, 13), False)]
    assert "SEMINE 13/10/2026" in capsys.readouterr().out
