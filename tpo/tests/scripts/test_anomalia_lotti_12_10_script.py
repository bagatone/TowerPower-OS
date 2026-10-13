"""Rimozione della nota di anomalia dai lotti Hyfarm (12/10/2026): mostra il testo, tutto o niente, audit, ripristino."""
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "commissioning" / "2026-10-12_anomalia_lotti.py"


def _module():
    spec = importlib.util.spec_from_file_location("anomalia_lotti_12_10", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeConn:
    """Un cursore finto con due lotti; registra le scritture."""
    def __init__(self, lotti, audit=None, rowcount=1):
        self.lotti = lotti            # public_id -> [id, version, anomalia, residuo, fornitore, referenza]
        self.audit = audit or {}
        self.rowcount, self.writes, self.committed, self.rolled = rowcount, [], False, False
        self._last = None

    def cursor(self): return self
    def commit(self): self.committed = True
    def rollback(self): self.rolled = True

    def execute(self, sql, args=()):
        self._last = (sql, args)
        if sql.lstrip().startswith(("UPDATE", "INSERT")):
            self.writes.append((sql.split()[0], args))

    def fetchone(self):
        sql, args = self._last
        if "FROM tpo.lotti_seme" in sql:
            return self.lotti.get(args[0])
        if "FROM tpo.audit_eventi" in sql:
            return self.audit.get(args[0])
        return None


def lotti(a16="senza etichetta, dichiarato a voce", a17="senza etichetta"):
    return {"LSE-000016": [16, 0, a16, 740, "Hyfarm", "Col Roja"], "LSE-000017": [17, 0, a17, 100, "Hyfarm", "Girasoli"]}


def test_preview_shows_the_exact_text_and_writes_nothing():
    module, conn, out = _module(), FakeConn(lotti()), []
    assert module.rimuovi(conn, ["LSE-000016", "LSE-000017"], False, out.append) == 0
    text = "\n".join(out)
    assert "'senza etichetta, dichiarato a voce'" in text and "--ripristina" in text and conn.writes == []


def test_execute_clears_and_audits_with_the_original_text_then_commits_once():
    module, conn, out = _module(), FakeConn(lotti()), []
    assert module.rimuovi(conn, ["LSE-000016", "LSE-000017"], True, out.append) == 0
    kinds = [k for k, _ in conn.writes]
    assert kinds == ["UPDATE", "INSERT", "UPDATE", "INSERT"] and conn.committed and not conn.rolled
    audit = conn.writes[1][1]
    assert "senza etichetta, dichiarato a voce" in audit[2] and audit[1] == "LSE-000016"   # reason contiene il testo originale


def test_lots_without_anomaly_are_skipped_and_concurrent_change_rolls_back():
    module = _module()
    conn, out = FakeConn(lotti(a16=None, a17=None)), []
    assert module.rimuovi(conn, ["LSE-000016", "LSE-000017"], True, out.append) == 0 and conn.writes == []
    conn = FakeConn(lotti(), rowcount=0)
    out = []
    assert module.rimuovi(conn, ["LSE-000016"], True, out.append) == 1 and conn.rolled and not conn.committed


def test_restore_puts_back_the_audited_text_only():
    module = _module()
    conn = FakeConn(lotti(a16=None, a17=None), audit={"LSE-000016": ("nota originale",)})
    out = []
    assert module.ripristina(conn, ["LSE-000016", "LSE-000017"], True, out.append) == 0
    assert [k for k, _ in conn.writes] == ["UPDATE", "INSERT"] and conn.writes[0][1][0] == "nota originale"
    assert conn.committed and "non risulta nessuna rimozione" in "\n".join(out)
