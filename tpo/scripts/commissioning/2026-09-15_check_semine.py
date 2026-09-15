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
        cur.execute("SELECT COUNT(*) FROM tpo.semine")
        print("TOTALE SEMINE:", cur.fetchone()[0])
        cur.execute("""SELECT s.public_id, s.codice_tracciabilita, s.stato, l.public_id
                       FROM tpo.semine s JOIN tpo.lotti_seme l ON l.id=s.lotto_seme_id
                       ORDER BY s.id""")
        for row in cur.fetchall():
            print(row)
finally:
    conn.close()
