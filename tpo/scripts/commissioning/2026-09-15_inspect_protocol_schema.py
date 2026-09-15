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
        for table in ("varieta", "cultivar", "cultivar_usi", "protocolli", "protocollo_versioni"):
            cur.execute("""SELECT column_name, data_type FROM information_schema.columns
                          WHERE table_schema='tpo' AND table_name=%s ORDER BY ordinal_position""", (table,))
            print(f"--- {table} ---")
            for r in cur.fetchall():
                print(" ", r)
        print("=== esempio Cilantro (PV-000003) completo ===")
        cur.execute("""
            SELECT v.public_id, v.denominazione, v.codice_tracciabilita, v.stato,
                   c.public_id, c.denominazione, c.stato,
                   cu.public_id, cu.stato_validazione,
                   p.public_id, p.denominazione, p.tipo, p.attivo,
                   pv.*
            FROM tpo.varieta v
            JOIN tpo.cultivar c ON c.varieta_id=v.id
            JOIN tpo.cultivar_usi cu ON cu.cultivar_id=c.id
            JOIN tpo.protocolli p ON p.cultivar_uso_id=cu.id
            JOIN tpo.protocollo_versioni pv ON pv.protocollo_id=p.id
            WHERE v.public_id='VAR-000003'
        """)
        for row in cur.fetchall():
            print(row)
finally:
    conn.close()
