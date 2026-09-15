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
        cur.execute("""SELECT column_name FROM information_schema.columns
                       WHERE table_schema='tpo' AND table_name='semente_impieghi'
                       ORDER BY ordinal_position""")
        print("COLONNE semente_impieghi:", [r[0] for r in cur.fetchall()])
        cur.execute("SELECT COUNT(*) FROM tpo.semente_impieghi")
        print("TOTALE semente_impieghi:", cur.fetchone()[0])
        cur.execute("SELECT * FROM tpo.semente_impieghi")
        for row in cur.fetchall():
            print(row)
finally:
    conn.close()
