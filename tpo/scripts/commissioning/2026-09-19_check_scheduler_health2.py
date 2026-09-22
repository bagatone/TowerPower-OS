import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg
parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)

def run(title, sql, params=()):
    print(f"=== {title} ===")
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description] if cur.description else []
            if cols:
                print(cols)
            rows = cur.fetchall()
            print(f"({len(rows)} righe)")
            for row in rows:
                print(row)
    except Exception as exc:
        conn.rollback()
        print("ERRORE:", repr(exc))
    print()

try:
    run(
        "RUNS scheduling (ordini) - tutti, piu' recenti prima",
        "SELECT public_id, started_at, completed_at, simulation, state, ordini_generati, "
        "elementi_saltati, created_by FROM tpo.runs ORDER BY started_at DESC LIMIT 15",
    )
    run(
        "RUNS production_planning - tutti, piu' recenti prima",
        "SELECT public_id, started_at, completed_at, state, created_by FROM tpo.production_planning_runs "
        "ORDER BY started_at DESC LIMIT 15",
    )
    run(
        "Ordini per El Callao / Azul y Sal, sempre (non solo 21gg)",
        "SELECT o.public_id, c.denominazione, o.data_ordine, o.created_at FROM tpo.ordini o "
        "JOIN tpo.clienti c ON c.id=o.cliente_id WHERE c.denominazione ILIKE %s OR c.denominazione ILIKE %s "
        "ORDER BY o.created_at DESC",
        ("%callao%", "%azul%sal%"),
    )
finally:
    conn.close()
