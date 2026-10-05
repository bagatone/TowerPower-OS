"""Elimina dal piano le allocazioni STOCK obsolete (5/10/2026, richiesta di Matteo).

Le 3 allocazioni (ALL-000065, ALL-000067, ALL-000068) riservano stock di merce che e' stata VENDUTA
fuori sistema: lo stock reale e' 0 e ogni nuova pianificazione si ferma con RESOURCE_OVERALLOCATED.
Matteo non ricorda i compratori: la vendita resta NON registrata e il motivo lo dice esplicitamente.

Cosa fa (solo queste allocazioni, tutto o niente, una transazione):
  - una transizione INVALIDA per l'intero residuo (registro append-only)
  - allocazione -> stato INVALIDA (versione +1)
  - un evento di audit per allocazione
Cosa NON fa: non crea revisioni di piano, non tocca ordini, righe d'ordine, stock, semine, movimenti,
consegne. Rifiuta qualsiasi allocazione che non sia STOCK, ATTIVA e realmente sovra-allocata.

Senza --esegui NON scrive nulla (anteprima). Non ripetibile (la seconda volta rifiuta: gia' INVALIDA).

Uso:
  .venv/bin/python scripts/commissioning/2026-10-05_invalida_stock_obsoleto.py            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-05_invalida_stock_obsoleto.py --esegui
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

from src.tpo_core.infrastructure.postgresql.allocation_invalidation import (  # noqa: E402
    AllocationInvalidationError, invalidate, preview,
)

DEFAULT_ALLOCATIONS = ("ALL-000065", "ALL-000067", "ALL-000068")
ACTOR = "matteo"
REASON = "stock venduto, vendita non registrata, dichiarato da Matteo il 5/10/2026"
CORRELATION = "invalida-stock-obsoleto-2026-10-05"
PROVENANCE = "commissioning:2026-10-05_invalida_stock_obsoleto"


def _describe(cursor, ids):
    cursor.execute(
        """SELECT a.public_id,a.quantity,a.unita_misura::text,a.state,a.version,pr.public_id,
                  ro.public_id,o.public_id,o.stato::text,o.data_consegna_prevista,cl.denominazione,
                  v.denominazione
           FROM tpo.allocazioni a
           JOIN tpo.righe_piano_semina rps ON rps.id=a.riga_piano_semina_id
           JOIN tpo.piano_produzione_revisioni pr ON pr.id=rps.piano_revisione_id
           JOIN tpo.righe_ordine ro ON ro.id=rps.riga_ordine_id
           JOIN tpo.ordini o ON o.id=ro.ordine_id
           JOIN tpo.clienti cl ON cl.id=o.cliente_id
           JOIN tpo.varieta v ON v.id=ro.varieta_id
           WHERE a.public_id = ANY(%s) ORDER BY a.public_id""", (list(ids),))
    return cursor.fetchall()


def run(conn, ids, esegui: bool, out=print) -> int:
    """Anteprima o esecuzione su una connessione psycopg gia' aperta (non in autocommit)."""
    cur = conn.cursor()
    try:
        candidates = preview(cur, ids)
    except AllocationInvalidationError as exc:
        conn.rollback()
        out(f"RIFIUTATO (nulla scritto): {exc}")
        return 2
    out("== ALLOCAZIONI CHE VERRANNO INVALIDATE")
    out("alloc | qta | stato | ver | revisione | riga | ordine (stato, consegna prevista) | cliente | varieta")
    for r in _describe(cur, ids):
        out(f"{r[0]} | {r[1]} {r[2]} | {r[3]} | v{r[4]} | {r[5]} | {r[6]} | {r[7]} ({r[8]}, {r[9]}) | {r[10]} | {r[11]}")
    out("\nStock per varieta' (disponibile | allocato attivo | scoperto):")
    seen = set()
    for c in candidates:
        if (c.variety, c.unit) in seen:
            continue
        seen.add((c.variety, c.unit))
        out(f"  {c.variety}: {c.stock_available} | {c.stock_active_allocated} | "
            f"{c.stock_active_allocated - c.stock_available} {c.unit}")
    out(f"Motivo registrato: {REASON}")
    out("Non vengono toccati: piani, ordini, righe d'ordine, stock, semine, movimenti, consegne.")
    if not esegui:
        conn.rollback()
        out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        return 0
    try:
        done = invalidate(cur, allocation_public_ids=ids, actor=ACTOR, reason=REASON,
                          correlation_id=CORRELATION, provenance=PROVENANCE)
        conn.commit()
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: {len(done)} allocazioni invalidate: {', '.join(i.public_id for i in done)}")
    cur.execute("SELECT public_id,state,version FROM tpo.allocazioni WHERE public_id = ANY(%s) ORDER BY 1",
                (list(ids),))
    for r in cur.fetchall():
        out(f"  {r[0]} -> {r[1]} (v{r[2]})")
    out("Ora puoi rilanciare la pianificazione: RESOURCE_OVERALLOCATED non deve piu' comparire.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true")
    ap.add_argument("--allocazione", action="append",
                    help="ALL-xxxxxx (ripetibile). Default: ALL-000065 ALL-000067 ALL-000068")
    a = ap.parse_args()
    ids = tuple(sorted(set(a.allocazione or DEFAULT_ALLOCATIONS)))

    from secret_boundary import load_postgresql_parameters  # noqa: E402
    import psycopg  # noqa: E402
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"],
                           connect_timeout=p["connect_timeout"])
    try:
        return run(conn, ids, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
