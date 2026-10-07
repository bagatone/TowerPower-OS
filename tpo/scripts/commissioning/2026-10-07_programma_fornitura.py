"""SOLA LETTURA - un programma di fornitura: versioni, righe con ricorrenza e TUTTI gli ordini che ha generato.

Serve a capire perche' un programma produce certi ordini (es. due ordini nella stessa data dallo stesso
programma). Non scrive nulla.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-07_programma_fornitura.py PF-000005
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

SQL_PROGRAM = """SELECT pf.id, pf.public_id, cl.denominazione, pf.created_at, pf.created_by
FROM tpo.programmi_fornitura pf JOIN tpo.clienti cl ON cl.id=pf.cliente_id WHERE pf.public_id=%s"""
SQL_VERSIONS = """SELECT id, numero_versione, stato::text, data_inizio, data_fine, orario_generazione,
       finestra_operativa_giorni, valida_dal, valida_al, created_by
FROM tpo.programmi_fornitura_versioni WHERE programma_fornitura_id=%s ORDER BY numero_versione"""
SQL_LINES = """SELECT rpf.posizione, v.denominazione, rpf.quantita, rpf.unita_misura::text, rpf.tipo_ricorrenza::text,
       rpf.intervallo_giorni,
       COALESCE((SELECT string_agg(g.giorno_iso::text, ',' ORDER BY g.giorno_iso)
                 FROM tpo.righe_programma_giorni g WHERE g.riga_programma_id=rpf.id),'')
FROM tpo.righe_programma_fornitura rpf JOIN tpo.varieta v ON v.id=rpf.varieta_id
WHERE rpf.programma_versione_id=%s ORDER BY rpf.posizione"""
SQL_ORDERS = """SELECT o.public_id, o.data_ordine, o.data_consegna_prevista, o.stato::text, o.tipo_creazione::text,
       o.created_at,
       COALESCE((SELECT string_agg(v.denominazione||' '||ro.quantita::numeric(20,2)::text||' '||ro.unita_misura::text,
                                   ', ' ORDER BY ro.posizione)
                 FROM tpo.righe_ordine ro JOIN tpo.varieta v ON v.id=ro.varieta_id WHERE ro.ordine_id=o.id),'')
FROM tpo.ordini o JOIN tpo.programmi_fornitura pf ON pf.id=o.programma_fornitura_id
WHERE pf.public_id=%s ORDER BY o.data_consegna_prevista, o.public_id"""


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def run(conn, public_id: str, out=print) -> int:
    cur = conn.cursor()
    cur.execute(SQL_PROGRAM, (public_id,))
    program = cur.fetchone()
    if not program:
        out(f"STOP: programma {public_id} inesistente.")
        return 2
    pk, pid, client, created_at, created_by = program
    out(f"== PROGRAMMA {pid} - {client} (creato {created_at:%Y-%m-%d %H:%M} da {created_by}) (NULLA E' STATO SCRITTO)")
    cur.execute(SQL_VERSIONS, (pk,))
    for vid, number, state, start, end, at, window, valid_from, valid_to, by in cur.fetchall():
        out(f"\n-- Versione {number}: {state}, dal {start} al {end or 'senza fine'}, generazione ore {at}, "
            f"finestra {window} giorni, valida {valid_from:%Y-%m-%d %H:%M} -> "
            f"{valid_to.strftime('%Y-%m-%d %H:%M') if valid_to else 'in corso'} (creata da {by})")
        out("   pos | varieta | quantita | ricorrenza | ogni X giorni | giorni ISO (1=lun)")
        cur.execute(SQL_LINES, (vid,))
        for pos, name, qty, uom, kind, interval, days in cur.fetchall():
            out(f"   {pos} | {name} | {_n(qty)} {uom} | {kind} | {interval or '-'} | {days or '-'}")
    cur.execute(SQL_ORDERS, (pid,))
    rows = cur.fetchall()
    out(f"\n-- Ordini generati da {pid} (tutti gli stati): {len(rows)}")
    out("   consegna | ordine | ordinato il | creato il | stato | origine | righe")
    for order, ordered_on, delivery, state, kind, created, lines in rows:
        out(f"   {delivery} | {order} | {ordered_on} | {created:%Y-%m-%d %H:%M} | {state} | {kind} | {lines}")
    return 0


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("PF-"):
        print(__doc__)
        return 2
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"],
                           connect_timeout=p["connect_timeout"], autocommit=True)
    conn.read_only = True
    try:
        return run(conn, sys.argv[1])
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
