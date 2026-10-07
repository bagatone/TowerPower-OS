"""Annulla ordini APERTI indicati ESPLICITAMENTE perche' errati (es. ordini generati con quantita' sbagliata).

Motivo tipico (7/10/2026, Matteo): ORD-000035 e ORD-000036 di Azul y Sal (PF-000005) sono 5 SET di Cilantro,
ma Azul y Sal ha 3 SET di consegna il venerdi': gli ordini giusti sono ORD-000042 e ORD-000043 (3 SET).

Stessa autorita' governata di `chiudi_ordini_scaduti` (order_cancellation), ma SOLO sugli ordini che nomini tu:
  - ogni ordine deve essere APERTO e senza nessuna consegna registrata (altrimenti si rifiuta);
  - ANNULLATO (versione +1, audit); le allocazioni ATTIVE sulle sue righe vengono RILASCIATE (append-only, audit);
  - se una allocazione RACCOLTA riguarda una raccolta non interamente caricata a stock, si ferma.
Non tocca stock, semine, movimenti, consegne, fatture, righe d'ordine ne' il programma di fornitura:
se il programma e' ancora configurato con la quantita' sbagliata, lo scheduler potrebbe rigenerare gli ordini.

Senza --esegui NON scrive nulla (anteprima). Tutto o niente, una transazione.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-07_annulla_ordini.py ORD-000035 ORD-000036            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-07_annulla_ordini.py ORD-000035 ORD-000036 --esegui
  opzione: --motivo "testo"   (default: ordine errato dichiarato da Matteo il 7/10/2026)
"""
import argparse
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

from src.tpo_core.infrastructure.postgresql.order_cancellation import (  # noqa: E402
    OrderCancellationError, cancel, preview, unsafe_harvest_allocations,
)

ACTOR = "matteo"
DEFAULT_REASON = ("ordine errato, dichiarato da Matteo il 7/10/2026 (quantita' non corrispondente alla fornitura "
                  "reale del cliente); annullato perche' non e' una richiesta valida. Nessuna consegna registrata.")
CORRELATION = "annulla-ordini-2026-10-07"
PROVENANCE = "commissioning:2026-10-07_annulla_ordini"


def _lines(cursor, pk):
    cursor.execute("""SELECT string_agg(v.denominazione||' '||ro.quantita||' '||ro.unita_misura::text, '; '
                             ORDER BY ro.posizione)
                      FROM tpo.righe_ordine ro JOIN tpo.varieta v ON v.id=ro.varieta_id WHERE ro.ordine_id=%s""", (pk,))
    return cursor.fetchone()[0]


def run(conn, order_ids, reason: str, esegui: bool, out=print) -> int:
    cur = conn.cursor()
    ids = tuple(sorted(set(order_ids)))
    try:
        from src.tpo_core.infrastructure.postgresql.order_cancellation import list_open
        found = list_open(cur, ids)
        latest = max((o.delivery_date for o in found if o.delivery_date), default=None)
        before = (latest + timedelta(days=1)) if latest else None
        if before is None:
            conn.rollback()
            out("STOP: ordini inesistenti o senza data di consegna prevista.")
            return 2
        orders, allocations = preview(cur, ids, before)
    except OrderCancellationError as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    out(f"== ORDINI CHE VERRANNO ANNULLATI ({len(orders)})")
    out("ordine | cliente | programma | consegna prevista | stato | righe")
    for o in orders:
        out(f"{o.public_id} | {o.customer} | {o.program or '-'} | {o.delivery_date} | {o.state} | {_lines(cur, o.pk)}")
    by_type = Counter()
    for a in allocations:
        by_type[(a.allocation_type, a.unit)] += a.remaining
    out(f"\n== ALLOCAZIONI ATTIVE CHE VERRANNO RILASCIATE ({len(allocations)})")
    for (kind, unit), qty in sorted(by_type.items()):
        out(f"  {kind}: {qty} {unit}")
    unsafe = unsafe_harvest_allocations(allocations)
    if unsafe:
        conn.rollback()
        out("\nSTOP (nulla scritto): alcune allocazioni RACCOLTA riguardano raccolte NON interamente caricate "
            "a stock. Serve una tua decisione.")
        return 3
    out(f"\nMotivo registrato: {reason}")
    out("Non vengono toccati: stock, semine, movimenti, consegne, fatture, programmi di fornitura, righe d'ordine.")
    if not esegui:
        conn.rollback()
        out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        return 0
    try:
        done, released = cancel(cur, order_public_ids=ids, before=before, actor=ACTOR, reason=reason,
                                correlation_id=CORRELATION, provenance=PROVENANCE)
        conn.commit()
    except OrderCancellationError as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: {len(done)} ordini ANNULLATI, {len(released)} allocazioni RILASCIATE.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ordini", nargs="+", help="ORD-000000 ... (obbligatori, nessun default)")
    ap.add_argument("--esegui", action="store_true")
    ap.add_argument("--motivo", default=DEFAULT_REASON)
    a = ap.parse_args()
    if not all(o.startswith("ORD-") for o in a.ordini):
        raise SystemExit("STOP: indica ordini nel formato ORD-000000.")
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, a.ordini, a.motivo, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
