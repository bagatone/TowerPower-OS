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
        "Ultime 10 esecuzioni Scheduling Engine (tpo.runs)",
        "SELECT id, stato, business_date, business_time, started_at, completed_at, note "
        "FROM tpo.runs ORDER BY id DESC LIMIT 10",
    )
    run(
        "Ultime 10 esecuzioni Production Planning (tpo.production_planning_runs)",
        "SELECT id, stato, business_at, started_at, completed_at, note "
        "FROM tpo.production_planning_runs ORDER BY id DESC LIMIT 10",
    )
    run(
        "Righe DA SEMINARE oggi (stato PIANIFICATA/PRONTA/TARDIVA), dalla revisione corrente",
        "SELECT rps.public_id, v.denominazione, cl.denominazione AS cliente, rps.stato, "
        "rps.sowing_at, rps.quantita_produttiva_autorizzata, rps.grammi_seme_richiesti, "
        "rps.data_consegna "
        "FROM tpo.righe_piano_semina rps "
        "JOIN tpo.varieta v ON v.id = rps.varieta_id "
        "JOIN tpo.piano_produzione_revisioni pvr ON pvr.id = rps.piano_revisione_id "
        "LEFT JOIN tpo.righe_ordine ro ON ro.id = rps.riga_ordine_id "
        "LEFT JOIN tpo.ordini o ON o.id = ro.ordine_id "
        "LEFT JOIN tpo.clienti cl ON cl.id = o.cliente_id "
        "WHERE pvr.sostituita_at IS NULL AND rps.stato IN ('PIANIFICATA','PRONTA','TARDIVA') "
        "ORDER BY rps.sowing_at ASC",
    )
finally:
    conn.close()
