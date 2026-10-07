"""SOLA LETTURA - allocazioni (attive e non) di uno o piu' ordini, con revisione di piano e riga d'ordine.

Serve a capire perche' l'anteprima di un annullamento rilascia piu' SET di quanti ne ha l'ordine: mostra
ogni allocazione con la revisione di piano a cui appartiene e se quella revisione e' quella CORRENTE.
Non scrive nulla.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-07_allocazioni_ordine.py ORD-000016
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

SQL = """
SELECT o.public_id, ro.public_id, v.denominazione, ro.quantita, rev.public_id, rev.numero_revisione,
       (pp.current_revision_id = rev.id), a.public_id, a.allocation_type::text, a.state::text, a.quantity,
       a.unita_misura::text,
       a.quantity - COALESCE((SELECT SUM(t.quantity) FROM tpo.transizioni_allocazione t
            WHERE t.allocation_id=a.id AND t.transition_type IN ('CONSUMATA','RILASCIATA','SOSTITUITA','INVALIDA')),0)
FROM tpo.allocazioni a
JOIN tpo.righe_piano_semina rps ON rps.id = a.riga_piano_semina_id
JOIN tpo.piano_produzione_revisioni rev ON rev.id = rps.piano_revisione_id
JOIN tpo.piani_produzione pp ON pp.id = rev.piano_produzione_id
JOIN tpo.righe_ordine ro ON ro.id = rps.riga_ordine_id
JOIN tpo.varieta v ON v.id = ro.varieta_id
JOIN tpo.ordini o ON o.id = ro.ordine_id
WHERE o.public_id = ANY(%s)
ORDER BY o.public_id, ro.posizione, rev.numero_revisione, a.public_id"""


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def run(conn, order_ids, out=print) -> int:
    cur = conn.cursor()
    cur.execute(SQL, (list(order_ids),))
    rows = cur.fetchall()
    out("== ALLOCAZIONI DEGLI ORDINI (NULLA E' STATO SCRITTO)")
    out("ordine | riga | varieta | ordinato | revisione piano | corrente? | allocazione | tipo | stato | quantita | residuo")
    tot_active = Decimal(0)
    for (order, line, name, ordered, rev, number, current, alloc, kind, state, qty, uom, rest) in rows:
        out(f"{order} | {line} | {name} | {_n(ordered)} | {rev} (n.{number}) | {'SI' if current else 'no'} | "
            f"{alloc} | {kind} | {state} | {_n(qty)} {uom} | {_n(rest)}")
        if state == "ATTIVA":
            tot_active += Decimal(rest)
    out(f"\nTOTALE residuo allocazioni ATTIVE: {_n(tot_active)}")
    return 0 if rows else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ordini", nargs="+")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"],
                           connect_timeout=p["connect_timeout"], autocommit=True)
    conn.read_only = True
    try:
        return run(conn, a.ordini)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
