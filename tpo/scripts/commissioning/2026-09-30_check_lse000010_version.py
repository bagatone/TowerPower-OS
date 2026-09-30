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
with conn.cursor() as cur:
    cur.execute("SELECT public_id, version, quantita_residua, unita_misura FROM tpo.lotti_seme WHERE public_id = 'LSE-000010'")
    print(cur.fetchall())
    cur.execute(
        "SELECT s.public_id, s.stato, s.data_avvio "
        "FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id "
        "WHERE v.codice_tracciabilita = 'RAB' AND s.data_avvio::date = '2026-09-26'"
    )
    print("semine 26/9 rabano gia' esistenti:", cur.fetchall())
conn.close()
