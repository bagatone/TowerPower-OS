"""SOLA LETTURA - produzione fisica in corso per varieta', come la vede il sistema (semine non chiuse).

Per ogni semina non chiusa: SET dichiarati (resa attesa compilata), SET gia' raccolti, SET ancora in produzione,
stato e finestra di raccolta. Poi il totale per varieta', da confrontare con il conteggio fisico:
  in produzione = attesi - raccolti; di cui "pronti" = finestra gia' iniziata (inizio <= adesso).
Le semine con resa attesa NON compilata compaiono come "NON COMPILATA" (il planner non le vede).

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-06_produzione_in_corso.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

SQL = """
SELECT v.denominazione, s.public_id, s.stato::text, s.data_avvio, s.quantita_seme,
       s.expected_useful_quantity, s.expected_useful_uom::text, s.harvest_window_start, s.harvest_window_end,
       COALESCE((SELECT SUM(rc.quantita) FROM tpo.raccolte rc WHERE rc.semina_id=s.id AND rc.unita_misura='SET'),0)
FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
WHERE s.stato<>'CHIUSA' ORDER BY v.denominazione, s.data_avvio, s.public_id"""


def _n(value: Decimal) -> str:
    return format(Decimal(value).normalize(), "f")


def run(conn, now: datetime | None = None, out=print) -> int:
    now = now or datetime.now().astimezone()
    cur = conn.cursor()
    cur.execute(SQL)
    rows = cur.fetchall()
    out(f"== PRODUZIONE IN CORSO al {now:%Y-%m-%d %H:%M} (NULLA E' STATO SCRITTO)")
    out("varieta | semina | stato | avviata | seme g | SET attesi | SET raccolti | in produzione | finestra raccolta | pronta?")
    tot: dict[str, dict] = defaultdict(lambda: {"att": Decimal(0), "rac": Decimal(0), "pronti": Decimal(0), "nc": 0, "next": None})
    for name, pid, stato, avvio, grams, exp, uom, w0, w1, harvested in rows:
        harvested = Decimal(harvested)
        t = tot[name]
        if exp is None or uom != "SET":
            t["nc"] += 1
            out(f"{name} | {pid} | {stato} | {avvio:%Y-%m-%d} | {_n(grams)} | NON COMPILATA | {_n(harvested)} | - | - | -")
            continue
        exp = Decimal(exp)
        residual = max(exp - harvested, Decimal(0))
        ready = w0 <= now
        t["att"] += exp
        t["rac"] += harvested
        if ready:
            t["pronti"] += residual
        elif t["next"] is None or w0 < t["next"]:
            t["next"] = w0
        out(f"{name} | {pid} | {stato} | {avvio:%Y-%m-%d} | {_n(grams)} | {_n(exp)} | {_n(harvested)} | {_n(residual)} | "
            f"{w0:%Y-%m-%d} -> {w1:%Y-%m-%d} | {'si' if ready else 'dal ' + format(w0, '%d/%m')}")
    out("\n== TOTALE PER VARIETA' (SET)")
    out("varieta | attesi | raccolti | in produzione | di cui pronti ora | semine non compilate | prossima pronta dal")
    for name in sorted(tot):
        t = tot[name]
        nxt = f"{t['next']:%d/%m}" if t["next"] else "-"
        out(f"{name} | {_n(t['att'])} | {_n(t['rac'])} | {_n(max(t['att'] - t['rac'], Decimal(0)))} | "
            f"{_n(t['pronti'])} | {t['nc']} | {nxt}")
    return 0


def main() -> int:
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"],
                           connect_timeout=p["connect_timeout"], autocommit=True)
    conn.read_only = True
    try:
        return run(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
