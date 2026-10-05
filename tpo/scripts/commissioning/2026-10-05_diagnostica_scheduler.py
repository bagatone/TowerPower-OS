"""Diagnostica di SOLA LETTURA dei due scheduler automatici (ordini e piano di
produzione): ultimi run nel database, LaunchAgent caricati (macOS) e ultime
righe dei log in runtime/logs. Non scrive e non modifica nulla.

Uso (dalla cartella del progetto):
    .venv/bin/python scripts/commissioning/2026-10-05_diagnostica_scheduler.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402
import psycopg  # noqa: E402

p = load_postgresql_parameters()
conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                       password=p["password"], sslmode=p["sslmode"],
                       connect_timeout=p["connect_timeout"], autocommit=True)
cur = conn.cursor()
print("== ULTIMI 8 RUN SCHEDULING ORDINI (tpo.runs)")
cur.execute("""SELECT public_id, state::text, simulation, started_at, completed_at, programmi_letti,
                      occorrenze_valutate, ordini_generati, elementi_saltati, created_by
               FROM tpo.runs ORDER BY id DESC LIMIT 8""")
print("run | stato | simulazione | inizio | fine | programmi | occorrenze | ordini | saltati | creato da")
for r in cur.fetchall():
    print(" | ".join("-" if x is None else str(x) for x in r))
print("\n== ULTIMI 8 RUN PIANO DI PRODUZIONE (tpo.production_planning_runs)")
cur.execute("""SELECT public_id, state::text, business_at, started_at, completed_at, ordini_letti,
                      righe_piano_generate, elementi_saltati, created_by
               FROM tpo.production_planning_runs ORDER BY id DESC LIMIT 8""")
print("run | stato | business_at | inizio | fine | ordini letti | righe piano | saltati | creato da")
for r in cur.fetchall():
    print(" | ".join("-" if x is None else str(x) for x in r))
print("\n== AUDIT piu' recenti con 'FAIL'/'ERROR' nel motivo (ultimi 5)")
cur.execute("""SELECT occurred_at, entity_type, entity_public_id, operation, left(coalesce(reason,''), 160)
               FROM tpo.audit_eventi WHERE reason ILIKE '%fail%' OR reason ILIKE '%error%' OR reason ILIKE '%errore%'
               ORDER BY id DESC LIMIT 5""")
rows = cur.fetchall()
for r in rows:
    print(" | ".join(str(x) for x in r))
if not rows:
    print("(nessuno)")
conn.close()

print("\n== LAUNCHAGENT (macOS)")
for label in ("com.towerpower.operational-scheduler", "com.towerpower.production-planning-scheduler"):
    try:
        out = subprocess.run(["launchctl", "print", f"gui/{subprocess.run(['id', '-u'], capture_output=True, text=True).stdout.strip()}/{label}"],
                             capture_output=True, text=True, timeout=15)
        if out.returncode != 0:
            print(f"{label}: NON caricato ({out.stderr.strip()[:120]})")
        else:
            keep = [l.strip() for l in out.stdout.splitlines()
                    if any(k in l for k in ("state =", "last exit code", "runs =", "run interval", "program =", "path ="))]
            print(f"{label}: caricato\n   " + "\n   ".join(keep[:8]))
    except Exception as exc:  # noqa: BLE001
        print(f"{label}: impossibile verificare ({type(exc).__name__})")

print("\n== LOG (runtime/logs): file piu' recenti e ultime 25 righe")
logs = sorted((ROOT / "runtime" / "logs").glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)[:4]
if not logs:
    print("(nessun file di log)")
for f in logs:
    print(f"\n--- {f.name}  (modificato {__import__('datetime').datetime.fromtimestamp(f.stat().st_mtime):%Y-%m-%d %H:%M})")
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]:
        print("   " + line[:220])
