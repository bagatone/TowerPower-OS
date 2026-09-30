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
        "Colonne reali di tpo.runs",
        "SELECT column_name FROM information_schema.columns WHERE table_schema='tpo' AND table_name='runs' ORDER BY ordinal_position",
    )
    run(
        "Ultime 10 esecuzioni Scheduling Engine (tpo.runs)",
        "SELECT id, state, business_date, business_time, started_at, completed_at "
        "FROM tpo.runs ORDER BY id DESC LIMIT 10",
    )
    run(
        "Colonne reali di tpo.production_planning_runs",
        "SELECT column_name FROM information_schema.columns WHERE table_schema='tpo' AND table_name='production_planning_runs' ORDER BY ordinal_position",
    )
    run(
        "Ultime 10 esecuzioni Production Planning (tpo.production_planning_runs)",
        "SELECT id, state, business_at, started_at, completed_at "
        "FROM tpo.production_planning_runs ORDER BY id DESC LIMIT 10",
    )
    run(
        "Revisioni piano produzione (tutte, per vedere se ne e' nata una nuova dopo RVP-000003)",
        "SELECT public_id, creata_il, sostituita_at FROM tpo.piano_produzione_revisioni ORDER BY id DESC LIMIT 10",
    )
finally:
    conn.close()
