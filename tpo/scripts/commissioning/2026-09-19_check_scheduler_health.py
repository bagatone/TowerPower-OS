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
    run("Totale ORDINI nel sistema (mai, non solo 21 giorni)", "SELECT count(*) FROM tpo.ordini")
    run("Ultimi 5 ORDINI (qualunque cliente)", "SELECT o.public_id, c.denominazione, o.data_ordine, o.created_at FROM tpo.ordini o JOIN tpo.clienti c ON c.id=o.cliente_id ORDER BY o.created_at DESC LIMIT 5")
    run("Totale RIGHE_PIANO_SEMINA (output di Production Planning)", "SELECT count(*) FROM tpo.righe_piano_semina")
    run("Ultime 5 righe_piano_semina (qualunque stato)", "SELECT public_id, stato, sowing_at, created_at FROM tpo.righe_piano_semina ORDER BY created_at DESC LIMIT 5")
    run("Totale RACCOLTE nel sistema (mai)", "SELECT count(*) FROM tpo.raccolte")
    run("Totale RUNS (scheduling + production planning, tutti)", "SELECT tipo, count(*) FROM tpo.runs GROUP BY tipo")
    run("Ultimi 10 RUNS (qualunque tipo/esito)", "SELECT public_id, tipo, stato, business_date, created_at FROM tpo.runs ORDER BY created_at DESC LIMIT 10")
finally:
    conn.close()
