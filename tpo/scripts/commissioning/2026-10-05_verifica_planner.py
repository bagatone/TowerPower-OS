"""Verifica del planner dopo la pulizia di ordini e allocazioni (5/10/2026).

Senza --esegui e' di SOLA LETTURA: controlla che i dati siano pronti e stampa il comando che lancerebbe.
Con --esegui lancia davvero il planning (`tpo production-planning initial`, scrive una revisione di piano:
e' un'operazione di produzione, la lanci tu) e poi riporta esito, contatori, messaggi e controlli finali.

Controlli PRIMA (devono essere tutti OK perche' il planner parta pulito):
  1. nessuna allocazione STOCK attiva supera lo stock disponibile (causa di RESOURCE_OVERALLOCATED);
  2. nessuna allocazione RACCOLTA attiva su raccolte non caricate a stock;
  3. nessuna allocazione STOCK/RACCOLTA attiva su ordini chiusi o annullati (le DOMANDA sono solo segnalate);
  4. nessun ordine aperto con consegna prevista prima del 3/10 (a parte quelli che dici tu).
Dopo il run: stato del run (COMMITTED atteso), contatori, eventuali errori, allocazioni attive per tipo.

Uso:
  .venv/bin/python scripts/commissioning/2026-10-05_verifica_planner.py            # solo controlli
  .venv/bin/python scripts/commissioning/2026-10-05_verifica_planner.py --esegui   # lancia il planning
  opzione: --business-at 2026-10-05T19:00:00+01:00   (default: adesso, fuso Atlantic/Canary, al minuto)

Perche' "adesso" e non l'occorrenza saltata delle 06:30: il planner rifiuta un istante di riferimento
PRECEDENTE a una raccolta registrata (RESOURCE_NOT_READY "RACCOLTA futura"); oggi le raccolte sono state
registrate dopo le 06:30 (es. albahaca alle 14:04). Quindi e' un run MANUALE con correlation-id proprio.
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
ACTOR = "matteo"
REASON = "Run manuale di verifica del planner dopo la pulizia di ordini e allocazioni del 5/10/2026"
CUTOFF = "2026-10-03"


def _rows(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchall()


def checks(cur, out) -> bool:
    ok = True
    over = _rows(cur, """
        SELECT v.denominazione, ast.stock_unita_misura::text,
               SUM(a.quantity - COALESCE((SELECT SUM(t.quantity) FROM tpo.transizioni_allocazione t
                    WHERE t.allocation_id=a.id),0)) AS allocato,
               COALESCE(MAX(st.disponibile),0)
        FROM tpo.allocazioni a JOIN tpo.allocazioni_stock ast ON ast.allocation_id=a.id
        JOIN tpo.varieta v ON v.id=ast.stock_varieta_id
        LEFT JOIN tpo.stock st ON st.varieta_id=ast.stock_varieta_id AND st.unita_misura=ast.stock_unita_misura
        WHERE a.state='ATTIVA' GROUP BY v.denominazione, ast.stock_unita_misura
        HAVING SUM(a.quantity - COALESCE((SELECT SUM(t.quantity) FROM tpo.transizioni_allocazione t
                    WHERE t.allocation_id=a.id),0)) > COALESCE(MAX(st.disponibile),0)""")
    out("1. Allocazioni STOCK attive oltre lo stock disponibile: " + ("nessuna  OK" if not over else "PROBLEMA"))
    for r in over:
        out(f"     {r[0]} {r[1]}: allocato {r[2]} > disponibile {r[3]}")
    ok &= not over

    unloaded = _rows(cur, """
        SELECT a.public_id, rc.public_id, o.public_id
        FROM tpo.allocazioni a JOIN tpo.allocazioni_raccolta ar ON ar.allocation_id=a.id
        JOIN tpo.raccolte rc ON rc.id=ar.raccolta_id
        JOIN tpo.righe_piano_semina l ON l.id=a.riga_piano_semina_id
        JOIN tpo.righe_ordine ro ON ro.id=l.riga_ordine_id JOIN tpo.ordini o ON o.id=ro.ordine_id
        WHERE a.state='ATTIVA' AND COALESCE((SELECT SUM(m.quantita) FROM tpo.movimenti_magazzino m
              WHERE m.raccolta_id=rc.id AND m.tipo='CARICO' AND m.unita_misura=rc.unita_misura),0) < rc.quantita""")
    out("2. Allocazioni RACCOLTA attive su raccolte non caricate a stock: " + ("nessuna  OK" if not unloaded else "PROBLEMA"))
    for r in unloaded:
        out(f"     {r[0]} (raccolta {r[1]}, ordine {r[2]})")
    ok &= not unloaded

    stale = _rows(cur, """
        SELECT a.public_id, a.allocation_type, o.public_id, o.stato::text
        FROM tpo.allocazioni a JOIN tpo.righe_piano_semina l ON l.id=a.riga_piano_semina_id
        JOIN tpo.righe_ordine ro ON ro.id=l.riga_ordine_id JOIN tpo.ordini o ON o.id=ro.ordine_id
        WHERE a.state='ATTIVA' AND o.stato NOT IN ('APERTO','PARZIALMENTE_EVASO')
        ORDER BY a.public_id""")
    holding = [r for r in stale if r[1] in ("STOCK", "RACCOLTA")]
    demand = [r for r in stale if r[1] not in ("STOCK", "RACCOLTA")]
    out("3. Allocazioni STOCK/RACCOLTA attive su ordini chiusi/annullati (trattengono merce): "
        + ("nessuna  OK" if not holding else "PROBLEMA"))
    for r in holding[:20]:
        out(f"     {r[0]} {r[1]} -> {r[2]} ({r[3]})")
    ok &= not holding
    out(f"   (informativo) allocazioni DOMANDA ancora attive su ordini chiusi: {len(demand)} - non trattengono "
        "merce, il planner non le conta come risorsa" + ("" if not demand else ": "
        + ", ".join(f"{r[0]}->{r[2]}" for r in demand[:10])))

    old = _rows(cur, """SELECT public_id, stato::text, data_consegna_prevista FROM tpo.ordini
                        WHERE stato IN ('APERTO','PARZIALMENTE_EVASO') AND data_consegna_prevista < %s
                        ORDER BY data_consegna_prevista, public_id""", (CUTOFF,))
    out(f"4. Ordini aperti con consegna prevista prima del {CUTOFF}: " + ("nessuno  OK" if not old else "DA GUARDARE"))
    for r in old:
        out(f"     {r[0]} {r[1]} prevista {r[2]}")
    ok &= not old

    n = _rows(cur, "SELECT stato::text, count(*) FROM tpo.ordini GROUP BY stato ORDER BY 1")
    out("   Ordini per stato: " + ", ".join(f"{s} {c}" for s, c in n))
    return ok


def default_business_at() -> str:
    return datetime.now(ZoneInfo("Atlantic/Canary")).replace(second=0, microsecond=0).isoformat(timespec="seconds")


def check_harvest_not_after(cur, business_at: str, out) -> bool:
    row = _rows(cur, "SELECT public_id, data_raccolta FROM tpo.raccolte ORDER BY data_raccolta DESC, id DESC LIMIT 1")
    if not row:
        return True
    late = _rows(cur, "SELECT public_id, data_raccolta FROM tpo.raccolte WHERE data_raccolta > %s::timestamptz "
                      "ORDER BY data_raccolta", (business_at,))
    out(f"5. Raccolte registrate DOPO l'istante di riferimento {business_at}: "
        + ("nessuna  OK" if not late else "PROBLEMA (il planner le rifiuterebbe come 'RACCOLTA futura')"))
    for r in late:
        out(f"     {r[0]} del {r[1]}")
    return not late


def last_runs(cur, out, limit=4):
    out("\nUltimi run di pianificazione:")
    for r in _rows(cur, """SELECT public_id, state::text, business_at, completed_at::timestamp(0)
                           FROM tpo.production_planning_runs ORDER BY id DESC LIMIT %s""", (limit,)):
        out(f"  {r[0]} | {r[1]} | business_at {r[2]} | chiuso {r[3]}")


def report(cur, out) -> bool:
    run = _rows(cur, """SELECT id,public_id,state::text,business_at,ordini_letti,righe_ordine_valutate,
                        righe_coperte_integralmente,righe_coperte_parzialmente,righe_piano_generate,
                        allocazioni_generate,righe_tardive,righe_non_producibili,elementi_saltati
                        FROM tpo.production_planning_runs ORDER BY id DESC LIMIT 1""")
    if not run:
        out("Nessun run trovato.")
        return False
    r = run[0]
    out(f"\n== ULTIMO RUN: {r[1]} stato {r[2]} (business_at {r[3]})")
    out(f"   ordini letti {r[4]}, righe valutate {r[5]}, coperte integralmente {r[6]}, parzialmente {r[7]}, "
        f"righe di piano {r[8]}, allocazioni {r[9]}, tardive {r[10]}, non producibili {r[11]}, saltati {r[12]}")
    for m in _rows(cur, """SELECT tipo::text, failure_category::text, codice, messaggio
                           FROM tpo.production_planning_run_messaggi WHERE planning_run_id=%s ORDER BY posizione""", (r[0],)):
        out(f"   [{m[0]}{'/' + m[1] if m[1] else ''}] {m[2]}: {m[3]}")
    rev = _rows(cur, "SELECT public_id, numero_revisione FROM tpo.piano_produzione_revisioni "
                     "WHERE planning_run_id=%s", (r[0],))
    if rev:
        out(f"   Revisione di piano creata: {rev[0][0]} (n. {rev[0][1]})")
    out("   Allocazioni ATTIVE per tipo: " + ", ".join(
        f"{t} {c} ({q} SET/unita)" for t, c, q in _rows(cur, """
            SELECT a.allocation_type, count(*), SUM(a.quantity - COALESCE((SELECT SUM(t.quantity)
                   FROM tpo.transizioni_allocazione t WHERE t.allocation_id=a.id),0))
            FROM tpo.allocazioni a WHERE a.state='ATTIVA' GROUP BY 1 ORDER BY 1""")))
    return r[2] == "COMMITTED"


def run(conn, esegui: bool, business_at: str, out=print) -> int:
    cur = conn.cursor()
    out("== CONTROLLI PRIMA DEL RUN")
    ready = checks(cur, out)
    ready &= check_harvest_not_after(cur, business_at, out)
    last_runs(cur, out)
    args = ["production-planning", "initial", "--business-at", business_at, "--policy-set-code", "DEFAULT",
            "--policy-version", "1", "--actor", ACTOR, "--reason", REASON,
            "--correlation-id", f"production-planning-manual-v1:{business_at}"]
    out("\nComando: tpo " + " ".join(repr(a) if " " in a else a for a in args))
    if not esegui:
        conn.rollback()
        out("\nANTEPRIMA: nulla e' stato lanciato." + ("" if ready else
            " ATTENZIONE: ci sono problemi nei controlli sopra, il run probabilmente fallirebbe."))
        out("Per lanciare il planning aggiungi --esegui")
        return 0 if ready else 3
    if not ready:
        conn.rollback()
        out("\nSTOP: i controlli non sono tutti OK, non lancio il planning. Incollami l'output.")
        return 3
    conn.commit()
    done = subprocess.run([RUN, *args], capture_output=True, text=True)
    out("\n== OUTPUT DEL PLANNING (exit " + str(done.returncode) + ")")
    out(((done.stdout or "") + (done.stderr or "")).rstrip())
    committed = report(conn.cursor(), out)
    conn.commit()
    out("\nESITO: " + ("COMMITTED, il planner funziona sui dati ripuliti." if committed and done.returncode == 0
                       else "NON COMMITTED: incollami questo output."))
    return 0 if committed and done.returncode == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true")
    ap.add_argument("--business-at", default=None)
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, a.esegui, a.business_at or default_business_at())
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
