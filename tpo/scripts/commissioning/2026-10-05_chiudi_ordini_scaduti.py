"""Chiude gli ordini storici SCADUTI senza consegne (5/10/2026, richiesta di Matteo: "segna tutto come evaso").

Perche' ANNULLATO e non EVASO: il database ammette EVASO solo se ogni riga ha una consegna registrata
(vincolo ct_ordini_fulfilment_state). Inventare consegne mai registrate e' vietato. Lo stato ANNULLATO e'
l'unica chiusura onesta; il motivo registrato dice chiaramente che e' un ordine storico chiuso da Matteo.

Cosa fa (tutto o niente, una transazione):
  - ogni ordine APERTO con consegna prevista PRIMA della soglia (default 2026-10-03 = avvio pulito) e senza
    nessuna consegna -> ANNULLATO (versione +1, audit);
  - le allocazioni ATTIVE sulle sue righe (domanda di produzione, raccolte) -> RILASCIATE (append-only, audit).
Cosa NON fa: non tocca stock, semine, movimenti, consegne, fatture, programmi di fornitura, righe d'ordine,
ordini futuri (consegna prevista dalla soglia in poi) ne' ordini con consegne anche parziali.

Senza --esegui NON scrive nulla (anteprima).

Uso:
  .venv/bin/python scripts/commissioning/2026-10-05_chiudi_ordini_scaduti.py            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-05_chiudi_ordini_scaduti.py --esegui
"""
import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

from src.tpo_core.infrastructure.postgresql.order_cancellation import (  # noqa: E402
    OrderCancellationError, cancel, eligible, list_open,
)

ACTOR = "matteo"
REASON = ("ordine storico scaduto (precedente all'avvio pulito del 3/10), chiuso da Matteo il 5/10/2026 "
          "come evaso fuori sistema: nessuna consegna registrata a sistema, quindi stato ANNULLATO "
          "(EVASO richiede consegne registrate)")
CORRELATION = "chiudi-ordini-scaduti-2026-10-05"
PROVENANCE = "commissioning:2026-10-05_chiudi_ordini_scaduti"


def _lines(cursor, pk):
    cursor.execute("""SELECT string_agg(v.denominazione||' '||ro.quantita||' '||ro.unita_misura::text, '; ' ORDER BY ro.posizione)
                      FROM tpo.righe_ordine ro JOIN tpo.varieta v ON v.id=ro.varieta_id WHERE ro.ordine_id=%s""", (pk,))
    return cursor.fetchone()[0]


def run(conn, before: date, esegui: bool, out=print) -> int:
    cur = conn.cursor()
    ok, skipped = eligible(cur, before)
    everything = list_open(cur)
    future = [o for o in everything if o.delivery_date is not None and o.delivery_date >= before]
    out(f"Soglia: consegna prevista PRIMA del {before}")
    out(f"\n== ORDINI CHE VERRANNO ANNULLATI ({len(ok)})")
    out("ordine | cliente | programma | consegna prevista | righe")
    for o in ok:
        out(f"{o.public_id} | {o.customer} | {o.program or '-'} | {o.delivery_date} | {_lines(cur, o.pk)}")
    out(f"\n== SCADUTI MA NON CHIUDIBILI ({len(skipped)}) — restano come sono")
    for o in skipped:
        out(f"{o.public_id} | {o.customer} | {o.delivery_date} | {o.state} | consegne registrate: {o.delivery_rows}")
    out(f"\n== NON TOCCATI: ordini con consegna prevista dal {before} in poi: {len(future)}")
    if not ok:
        conn.rollback()
        out("\nNessun ordine da chiudere.")
        return 0
    from src.tpo_core.infrastructure.postgresql.order_cancellation import (
        allocations_to_release, unsafe_harvest_allocations)
    allocs = allocations_to_release(cur, tuple(o.pk for o in ok))
    by_type = Counter()
    for a in allocs:
        by_type[(a.allocation_type, a.unit)] += a.remaining
    out(f"\n== ALLOCAZIONI ATTIVE CHE VERRANNO RILASCIATE ({len(allocs)})")
    for (kind, unit), qty in sorted(by_type.items()):
        out(f"  {kind}: {qty} {unit}")
    for a in allocs:
        if a.allocation_type == "RACCOLTA":
            out(f"  RACCOLTA {a.public_id} ({a.source}) ordine {a.order}: {a.remaining} {a.unit} - "
                f"raccolta interamente caricata a stock: {'SI' if a.harvest_fully_loaded else 'NO'}")
    unsafe = unsafe_harvest_allocations(allocs)
    if unsafe:
        conn.rollback()
        out("\nSTOP (nulla scritto): alcune allocazioni RACCOLTA riguardano raccolte NON interamente caricate "
            "a stock; rilasciarle le renderebbe di nuovo disponibili come merce libera. Serve una tua decisione.")
        return 3
    out(f"\nMotivo registrato: {REASON}")
    out("Non vengono toccati: stock, semine, movimenti, consegne, fatture, programmi di fornitura, righe d'ordine.")
    if not esegui:
        conn.rollback()
        out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        return 0
    try:
        orders, released = cancel(cur, order_public_ids=tuple(o.public_id for o in ok), before=before,
                                  actor=ACTOR, reason=REASON, correlation_id=CORRELATION,
                                  provenance=PROVENANCE)
        conn.commit()
    except OrderCancellationError as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: {len(orders)} ordini ANNULLATI, {len(released)} allocazioni RILASCIATE.")
    out("Ora rilancia la pianificazione: il piano si rigenera solo con gli ordini ancora aperti.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true")
    ap.add_argument("--prima-del", default="2026-10-03", help="soglia esclusiva AAAA-MM-GG (default 2026-10-03)")
    a = ap.parse_args()
    before = date.fromisoformat(a.prima_del)
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, before, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
