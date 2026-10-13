"""SOLA LETTURA - dettaglio di uno o piu' ordini con CODICE DI TRACCIABILITA' (7/10/2026, richiesta di Matteo).

Per ogni ordine: cliente, date, stato, origine, righe, consegne registrate e, per ogni consegna, il codice di
tracciabilita' della semina da cui e' uscito il prodotto (catena riga consegna -> SCARICO -> consumi_lotto ->
CARICO -> raccolta -> semina, la stessa della bolla). Un ordine SENZA consegna non ha ancora un codice: il codice lo
assume la consegna, non l'ordine. In quel caso mostra anche lo stock per lotto e i movimenti recenti delle varieta'
dell'ordine, per capire cosa e' fisicamente uscito. Non scrive nulla.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-07_ordini_dettaglio.py ORD-000018 ORD-000044 ORD-000050
  .venv/bin/python scripts/commissioning/2026-10-07_ordini_dettaglio.py ORD-000018 --dal 2026-10-01
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

ORDER = """
SELECT o.id, o.public_id, cl.denominazione, o.data_ordine, o.data_consegna_prevista, o.stato::text,
       o.tipo_creazione::text, pf.public_id
FROM tpo.ordini o JOIN tpo.clienti cl ON cl.id=o.cliente_id
LEFT JOIN tpo.programmi_fornitura pf ON pf.id=o.programma_fornitura_id
WHERE o.public_id=%s"""

LINES = """
SELECT ro.id, ro.public_id, v.id, v.denominazione, v.codice_tracciabilita, ro.quantita, ro.unita_misura::text
FROM tpo.righe_ordine ro JOIN tpo.varieta v ON v.id=ro.varieta_id
WHERE ro.ordine_id=%s ORDER BY ro.id"""

DELIVERIES = """
SELECT c.public_id, c.stato::text, c.data_prevista, c.data_effettiva, rc.id, v.denominazione, rc.quantita,
       rc.unita_misura::text
FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id JOIN tpo.varieta v ON v.id=rc.varieta_id
WHERE rc.ordine_id=%s ORDER BY c.public_id, rc.posizione"""

ORIGINS = """
SELECT s.codice_tracciabilita, s.public_id, r.public_id, r.data_raccolta, cl.quantita
FROM tpo.movimenti_magazzino ms
JOIN tpo.consumi_lotto cl ON cl.movimento_scarico_id=ms.id AND cl.tipo_consumo='CONSEGNA'
JOIN tpo.movimenti_magazzino mc ON mc.id=cl.movimento_carico_id
JOIN tpo.raccolte r ON r.id=mc.raccolta_id
JOIN tpo.semine s ON s.id=r.semina_id
WHERE ms.riga_consegna_id=%s AND ms.tipo='SCARICO'
ORDER BY mc.data_movimento, mc.id"""

LOTS = """
SELECT mc.public_id, mc.data_movimento, mc.quantita, mc.quantita-COALESCE(SUM(cl.quantita),0),
       s.codice_tracciabilita, s.public_id, r.public_id
FROM tpo.movimenti_magazzino mc
JOIN tpo.raccolte r ON r.id=mc.raccolta_id JOIN tpo.semine s ON s.id=r.semina_id
LEFT JOIN tpo.consumi_lotto cl ON cl.movimento_carico_id=mc.id
WHERE mc.tipo='CARICO' AND mc.varieta_id=%s
GROUP BY mc.id, s.id, r.id
HAVING mc.quantita-COALESCE(SUM(cl.quantita),0) > 0
ORDER BY mc.data_movimento, mc.id"""

MOVEMENTS = """
SELECT mm.public_id, mm.data_movimento, mm.tipo::text, mm.direzione::text, mm.quantita, mm.origine_tipo,
       COALESCE(mm.origine_riferimento,''), mm.motivo
FROM tpo.movimenti_magazzino mm
WHERE mm.varieta_id=%s AND mm.data_movimento >= %s ORDER BY mm.data_movimento, mm.id"""

STOCK = "SELECT disponibile FROM tpo.stock WHERE varieta_id=%s AND unita_misura='SET'"


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def _variety_context(cur, variety_id: int, name: str, since: date, out) -> None:
    cur.execute(STOCK, (variety_id,))
    row = cur.fetchone()
    out(f"\n  -- {name}: stock disponibile {_n(row[0]) if row else '0'} SET (dato di sistema)")
    cur.execute(LOTS, (variety_id,))
    lots = cur.fetchall()
    out("  lotti con residuo (carico | data | caricati | residuo | codice tracciabilita' | semina | raccolta):")
    if not lots:
        out("    nessun lotto con residuo")
    for mov, when, qty, left, code, semina, raccolta in lots:
        out(f"    {mov} | {when:%Y-%m-%d %H:%M} | {_n(qty)} | {_n(left)} | {code or '(senza codice)'} | "
            f"{semina} | {raccolta}")
    cur.execute(MOVEMENTS, (variety_id, since))
    moves = cur.fetchall()
    out(f"  movimenti dal {since} (movimento | data | tipo | dir | quantita' | origine | riferimento | motivo):")
    if not moves:
        out("    nessuno")
    for mov, when, kind, direction, qty, origin, ref, reason in moves:
        out(f"    {mov} | {when:%Y-%m-%d %H:%M} | {kind} | {direction} | {_n(qty)} | {origin} | {ref} | {reason}")


def run(conn, orders, since: date, out=print) -> int:
    cur = conn.cursor()
    missing = 0
    shown_context: set[int] = set()
    for public_id in orders:
        cur.execute(ORDER, (public_id,))
        order = cur.fetchone()
        if order is None:
            out(f"\n== {public_id}: NON TROVATO")
            missing += 1
            continue
        pk, public, client, ordered_on, delivery, state, kind, program = order
        out(f"\n== {public} | {client} | ordinato il {ordered_on} | consegna prevista {delivery} | {state} | "
            f"{kind}{f' ({program})' if program else ''}   (NULLA E' STATO SCRITTO)")
        cur.execute(LINES, (pk,))
        lines = cur.fetchall()
        for _, line, _, name, variety_code, qty, unit in lines:
            out(f"  riga {line}: {name} {_n(qty)} {unit}  [codice varieta' {variety_code or '-'}]")
        cur.execute(DELIVERIES, (pk,))
        deliveries = cur.fetchall()
        if not deliveries:
            out("  Consegne registrate: NESSUNA -> nessun codice di tracciabilita' assegnato a questo ordine "
                "(il codice lo prende la consegna, dalla semina da cui esce il prodotto).")
            for _, _, variety_id, name, _, _, _ in lines:
                if variety_id not in shown_context:
                    shown_context.add(variety_id)
                    _variety_context(cur, variety_id, name, since, out)
            continue
        for consegna, cstate, planned, actual, rc_id, name, qty, unit in deliveries:
            out(f"  Consegna {consegna} ({cstate}, prevista {planned}, effettiva {actual or '-'}): "
                f"{name} {_n(qty)} {unit}")
            cur.execute(ORIGINS, (rc_id,))
            origins = cur.fetchall()
            if not origins:
                out("    codice di tracciabilita': NON RISOLVIBILE (nessuna catena di lotto con codice)")
            traced = Decimal(0)
            for code, semina, raccolta, harvested, quantity in origins:
                traced += Decimal(quantity)
                out(f"    codice {code} | semina {semina} | raccolta {raccolta} ({harvested}) | {_n(quantity)} {unit}")
            if origins and cstate == "CONSEGNATA" and traced < Decimal(qty):
                out(f"    senza origine: {_n(Decimal(qty) - traced)} {unit} (giacenza storica senza lotto tracciato)")
    return 2 if missing else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ordini", nargs="+")
    ap.add_argument("--dal", default="2026-10-01", help="data iniziale per i movimenti di magazzino (AAAA-MM-GG)")
    a = ap.parse_args()
    if not all(o.startswith("ORD-") for o in a.ordini):
        raise SystemExit("STOP: indica ordini nel formato ORD-000000.")
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        conn.read_only = True
        return run(conn, a.ordini, date.fromisoformat(a.dal))
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
