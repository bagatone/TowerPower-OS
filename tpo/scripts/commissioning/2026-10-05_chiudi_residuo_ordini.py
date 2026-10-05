"""Chiude il RESIDUO NON PIU' DOVUTO di ordini parzialmente evasi (5/10/2026, decisione di Matteo).

Un ordine PARZIALMENTE_EVASO non si puo' annullare (ha consegne) ne' evadere (ordinato > consegnato).
Se il residuo non e' piu' dovuto, la chiusura onesta e': per ogni riga la quantita' ordinata diventa quella
effettivamente CONSEGNATA (la quantita' originale resta nell'audit) e l'ordine passa a EVASO; le allocazioni
attive sulle sue righe vengono rilasciate. Tutto o niente, una transazione.

Non tocca consegne, righe di consegna, stock, semine, movimenti, fatture, programmi di fornitura.
Senza --esegui NON scrive nulla (anteprima).

Uso:
  .venv/bin/python scripts/commissioning/2026-10-05_chiudi_residuo_ordini.py            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-05_chiudi_residuo_ordini.py --esegui
  (default: ORD-000009 ORD-000014; altri ordini con --ordini ORD-... ORD-...)
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

from src.tpo_core.infrastructure.postgresql.order_residual_closure import (  # noqa: E402
    OrderResidualClosureError, close_residual, preview,
)
from src.tpo_core.infrastructure.postgresql.order_cancellation import unsafe_harvest_allocations  # noqa: E402

ACTOR = "matteo"
DEFAULT_ORDERS = ("ORD-000009", "ORD-000014")
REASON = ("residuo non piu' dovuto, dichiarato da Matteo il 5/10/2026: ordine parzialmente evaso e scaduto, "
          "il cliente non deve ricevere il residuo; quantita' ordinata portata a quella consegnata "
          "(quantita' originale conservata nell'audit)")
CORRELATION = "chiudi-residuo-ordini-2026-10-05"
PROVENANCE = "commissioning:2026-10-05_chiudi_residuo_ordini"


def run(conn, order_ids, esegui: bool, out=print) -> int:
    cur = conn.cursor()
    try:
        orders, allocs = preview(cur, tuple(order_ids))
    except OrderResidualClosureError as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    out(f"== ORDINI CON RESIDUO DA CHIUDERE ({len(orders)})")
    for o in orders:
        out(f"{o.public_id} | {o.customer} | consegna prevista {o.delivery_date} | {o.state} -> EVASO")
        for line in o.lines:
            out(f"    {line.public_id} {line.variety}: ordinato {line.ordered} {line.unit}, consegnato "
                f"{line.delivered}, residuo non piu' dovuto {line.residual} -> quantita' ordinata diventa {line.delivered}")
    out(f"\n== ALLOCAZIONI ATTIVE CHE VERRANNO RILASCIATE ({len(allocs)})")
    for a in allocs:
        extra = f" (raccolta {a.source}, interamente caricata a stock: {'SI' if a.harvest_fully_loaded else 'NO'})" \
            if a.allocation_type == "RACCOLTA" else ""
        out(f"  {a.public_id} {a.allocation_type} {a.remaining} {a.unit} ordine {a.order}{extra}")
    if unsafe_harvest_allocations(allocs):
        conn.rollback()
        out("\nSTOP (nulla scritto): c'e' un'allocazione RACCOLTA su una raccolta NON interamente caricata a stock; "
            "rilasciarla la renderebbe di nuovo disponibile come merce libera. Serve prima una tua decisione su "
            "quella raccolta (venduta? ancora fisicamente presente?).")
        return 3
    out(f"\nMotivo registrato: {REASON}")
    out("Non vengono toccati: consegne, righe di consegna, stock, semine, movimenti, fatture, programmi di fornitura.")
    if not esegui:
        conn.rollback()
        out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        return 0
    try:
        done, released = close_residual(cur, order_public_ids=tuple(order_ids), actor=ACTOR, reason=REASON,
                                        correlation_id=CORRELATION, provenance=PROVENANCE)
        conn.commit()
    except OrderResidualClosureError as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: {len(done)} ordini EVASI (residuo chiuso), {len(released)} allocazioni RILASCIATE.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true")
    ap.add_argument("--ordini", nargs="+", default=list(DEFAULT_ORDERS))
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, a.ordini, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
