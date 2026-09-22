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
        cur.execute(
            "SELECT public_id, anomalia, version, quantita_residua, unita_misura "
            "FROM tpo.lotti_seme WHERE public_id IN ('LSE-000010','LSE-000012','LSE-000013') "
            "ORDER BY public_id"
        )
        for row in cur.fetchall():
            print(row)
finally:
    conn.close()
