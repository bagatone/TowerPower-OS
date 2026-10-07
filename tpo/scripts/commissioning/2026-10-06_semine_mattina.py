"""Registra le semine REALI di Matteo del 6/10/2026, ore 09:00: 1 SET Mizuna, 1 SET Rucola, 1 SET Pak Choi.

Per ogni varieta', stessa procedura governata delle semine precedenti:
  1. `tpo semina commission` (stato AVVIATA, origin RIPRISTINO_STOCK, nessun cliente/ordine: si collega dopo);
     - grammi = grammi/SET della versione di protocollo APPROVATA corrente x SET dichiarati (non inventati);
     - lotto di seme scelto con la stessa logica di sempre e MOSTRATO prima di scrivere;
     - il codice di tracciabilita' (AAA-GGMM-L) e il SEM-... li genera il sistema: qui si stampano quelli veri.
  2. `tpo materiali consumo-semina` (4 vaschette + 4 substrati per SET, regola del 4/10).

Senza --esegui NON scrive nulla (anteprima). Rilanciabile: se la semina del giorno esiste gia' la salta e
il consumo materiali e' idempotente per semina (nessun doppio scarico).

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-06_semine_mattina.py            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-06_semine_mattina.py --esegui   # scrive
"""
import argparse
import importlib.util
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

_spec = importlib.util.spec_from_file_location(
    "commission_base", ROOT / "scripts" / "commissioning" / "2026-10-04_commission_semine_afila_cilantro.py")
base = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = base
_spec.loader.exec_module(base)

TZ = timezone(timedelta(hours=1))
RUN = base.RUN
DAY = date(2026, 10, 6)
SEMINE = [("Mizuna", 1), ("Rucola", 1), ("Pak Choi", 1)]  # (varieta', SET dichiarati da Matteo)
PROVENANCE = ('{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED",'
              '"selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}')


def shown(cmd):
    return " ".join(c if c and all(ch.isalnum() or ch in "-_./:+=,@" for ch in c) else repr(c) for c in cmd[1:])


def esegui(cmd, titolo):
    print(f"  $ tpo {shown(cmd)}")
    done = subprocess.run(cmd, capture_output=True, text=True)
    print(done.stdout.rstrip())
    if done.returncode != 0:
        print(done.stderr.rstrip(), file=sys.stderr)
        base.stop(f"{titolo} fallito (exit {done.returncode}); non rilancio altro.")


def find(cur, nome, giorno):
    cur.execute("""SELECT s.public_id, s.codice_tracciabilita FROM tpo.semine s
                   JOIN tpo.varieta v ON v.id=s.varieta_id
                   WHERE v.denominazione=%s AND s.data_avvio::date=%s ORDER BY s.id""", (nome, giorno))
    return cur.fetchall()


def run(conn, esegui_scrittura: bool, ora: str, giorno: date = DAY) -> list[tuple[str, int, str, str]]:
    base.TODAY = giorno  # scadenza lotti valutata alla data di semina
    h, m = (int(x) for x in ora.split(":"))
    started = datetime(giorno.year, giorno.month, giorno.day, h, m, tzinfo=TZ)
    cur = conn.cursor()
    risultato = []
    for nome, n_set in SEMINE:
        print(f"\n=== {nome}: {n_set} SET, avvio {started:%d/%m/%Y %H:%M} ===")
        esistenti = find(cur, nome, giorno)
        if len(esistenti) > 1:
            base.stop(f"piu' semine di {nome} il {giorno}: " + ", ".join(e[0] for e in esistenti))
        if esistenti:
            semina, codice = esistenti[0]
            print(f"  semina gia' registrata: {semina} ({codice}). Salto il commissioning.")
        else:
            pv, per_set = base.resolve_protocol(cur, nome)
            grams = per_set * n_set
            print(f"  protocollo {pv}: {per_set} g/SET x {n_set} SET = {grams} g")
            lse, lver = base.resolve_seed_lot(cur, nome, grams)
            slug = nome.lower().replace(" ", "-")
            reason = (f"Semina reale {nome} del {giorno:%d/%m/%Y} ore {ora} ({n_set} SET, {grams.normalize():f} g), "
                      "dichiarata da Matteo; cliente/ordine da assegnare in seguito.")
            cmd = [RUN, "semina", "commission", "--seed-lot", lse, "--expected-seed-lot-version", str(lver),
                   "--protocol-version", pv, "--actual-seed-grams", f"{grams.normalize():f}",
                   "--physical-started-at", started.isoformat(), "--origin", "RIPRISTINO_STOCK",
                   "--provenance", PROVENANCE, "--actor", "matteo", "--reason", reason,
                   "--correlation-id", f"SEMINA-{giorno}-{slug}", "--idempotency-key", f"semina-{slug}-{giorno}",
                   "--confirm"]
            if not esegui_scrittura:
                print(f"  (anteprima) $ tpo {shown(cmd)}")
                risultato.append((nome, n_set, "(sara' generato)", "(sara' generato)"))
                continue
            esegui(cmd, f"commissioning {nome}")
            trovate = find(cur, nome, giorno)
            if len(trovate) != 1:
                base.stop(f"dopo il commissioning di {nome} attesa 1 semina del {giorno}, trovate {len(trovate)}.")
            semina, codice = trovate[0]
        if esegui_scrittura:
            reason = (f"Consumo materiali semina {semina} ({codice}) {nome} {n_set} SET del "
                      f"{giorno:%d/%m/%Y}: 4 vaschette + 4 substrati per SET")
            esegui([RUN, "materiali", "consumo-semina", "--semina", semina, "--set", str(n_set),
                    "--actor", "matteo", "--reason", reason,
                    "--correlation-id", f"CONSUMO-{giorno}-{semina}", "--confirm"], f"consumo materiali {semina}")
        else:
            print(f"  (anteprima) consumo materiali per {semina}: {4 * n_set} vaschette + {4 * n_set} substrati")
        risultato.append((nome, n_set, semina, codice))
    return risultato


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: anteprima)")
    ap.add_argument("--ora", default="09:00", help="ora fisica di semina HH:MM (default 09:00)")
    a = ap.parse_args()
    print(f"== SEMINE {DAY} -- {'ESECUZIONE' if a.esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    conn = base.db()
    conn.autocommit = True
    try:
        risultato = run(conn, a.esegui, a.ora)
    finally:
        conn.close()
    print("\n== RIEPILOGO")
    for nome, n_set, semina, codice in risultato:
        print(f"  {nome:10} {n_set} SET  {semina}  {codice}")
    print("\n== FINE" + ("" if a.esegui else " (anteprima: nulla scritto; per scrivere aggiungi --esegui)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
