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
try:
    with conn.cursor() as cur:
        cur.execute("SELECT id, codice, denominazione, attivo FROM tpo.usi_produttivi")
        for row in cur.fetchall():
            print(row)
        cur.execute("SELECT MAX(public_id) FROM tpo.protocollo_versioni")
        print("ultimo PV public_id:", cur.fetchone()[0])
finally:
    conn.close()
