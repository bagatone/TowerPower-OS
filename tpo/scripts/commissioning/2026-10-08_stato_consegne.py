"""SOLA LETTURA - situazione per le consegne del giorno: giacenza, semine non chiuse e righe d'ordine aperte.

Per le varieta' indicate mostra la giacenza (SET), le semine non chiuse (stato, SET attesi/raccolti, finestra) e,
per i clienti indicati (anche parte del nome), i loro ordini aperti con le righe e il residuo. Se un cliente non
esiste lo dice. Non scrive nulla; serve a scegliere, con te, da quale semina esce ogni SET da consegnare.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-08_stato_consegne.py \\
      --varieta Afila Cilantro Basilico Rabano --clienti Tagoro Salvaje
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

SEMINE = """
SELECT s.public_id, s.codice_tracciabilita, s.stato::text, s.data_avvio, s.expected_useful_quantity,
       s.expected_useful_uom::text, s.harvest_window_start,
       COALESCE((SELECT SUM(r.quantita) FROM tpo.raccolte r WHERE r.semina_id=s.id AND r.unita_misura='SET'),0)
FROM tpo.semine s WHERE s.varieta_id=%s AND s.stato<>'CHIUSA' ORDER BY s.data_avvio, s.public_id"""

ORDINI = """
SELECT o.public_id, ro.public_id, o.data_consegna_prevista, o.stato::text, o.tipo_creazione::text, pf.public_id,
       v.denominazione, ro.quantita,
       ro.quantita - COALESCE((SELECT SUM(rc.quantita) FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id
                               WHERE rc.riga_ordine_id=ro.id AND c.stato='CONSEGNATA'),0)
FROM tpo.ordini o JOIN tpo.righe_ordine ro ON ro.ordine_id=o.id JOIN tpo.varieta v ON v.id=ro.varieta_id
LEFT JOIN tpo.programmi_fornitura pf ON pf.id=o.programma_fornitura_id
WHERE o.cliente_id=%s AND o.stato IN ('APERTO','PARZIALMENTE_EVASO')
ORDER BY o.data_consegna_prevista, o.public_id, ro.public_id"""


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").strip()


def run(conn, varieties, clients, out=print) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id, denominazione FROM tpo.varieta")
    known = {_fold(name): (vid, name) for vid, name in cur.fetchall()}
    unknown = [v for v in varieties if _fold(v) not in known]
    if unknown:
        out(f"STOP: varieta' sconosciute: {', '.join(unknown)}")
        return 2
    out(f"== SITUAZIONE CONSEGNE al {datetime.now().astimezone():%Y-%m-%d %H:%M} (NULLA E' STATO SCRITTO)")
    for item in varieties:
        vid, name = known[_fold(item)]
        cur.execute("SELECT COALESCE(sum(disponibile),0) FROM tpo.stock WHERE varieta_id=%s AND unita_misura='SET'", (vid,))
        out(f"\n-- {name}: giacenza {_n(cur.fetchone()[0])} SET")
        cur.execute(SEMINE, (vid,))
        rows = cur.fetchall()
        if not rows:
            out("   nessuna semina non chiusa")
        for pid, code, state, start, exp, uom, window, harvested in rows:
            expected = f"{_n(exp)} {uom}" if exp is not None else "NON COMPILATA"
            tail = f" | finestra dal {window:%Y-%m-%d}" if window else ""
            out(f"   {pid} | {code} | {state} | avviata {start:%Y-%m-%d} | attesi {expected} | "
                f"raccolti {_n(harvested)} SET{tail}")
    for wanted in clients:
        cur.execute("SELECT id, public_id, denominazione FROM tpo.clienti")
        matches = [r for r in cur.fetchall() if _fold(wanted) in _fold(r[2])]
        if not matches:
            out(f"\n== CLIENTE '{wanted}': NON ESISTE nel sistema (andrebbe registrato come cliente prima dell'ordine)")
            continue
        for cid, public, name in matches:
            out(f"\n== CLIENTE {name} ({public}) - ordini aperti")
            cur.execute(ORDINI, (cid,))
            orders = cur.fetchall()
            if not orders:
                out("   nessun ordine aperto")
            for order, line, delivery, state, kind, program, variety, qty, residual in orders:
                out(f"   consegna {delivery} | {order} {line} | {variety} {_n(qty)} SET (residuo {_n(residual)}) | "
                    f"{state} | {kind}{f' ({program})' if program else ''}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--varieta", nargs="+", required=True)
    ap.add_argument("--clienti", nargs="*", default=[])
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        conn.read_only = True
        return run(conn, a.varieta, a.clienti)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
