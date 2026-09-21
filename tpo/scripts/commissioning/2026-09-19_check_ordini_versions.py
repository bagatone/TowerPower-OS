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
cur = conn.cursor()

for ord_pid in ("ORD-000014", "ORD-000009", "ORD-000010"):
    cur.execute(
        """SELECT o.id, o.public_id, o.version, o.stato
           FROM tpo.ordini o WHERE o.public_id=%s""",
        (ord_pid,),
    )
    row = cur.fetchone()
    if row is None:
        print(f"{ord_pid}: NON TROVATO")
        continue
    ord_id, ord_public, ord_version, stato = row
    print(f"{ord_pid}: id={ord_id} version={ord_version} stato={stato}")
    cur.execute(
        """SELECT ro.public_id, ro.version, v.denominazione, ro.quantita, ro.unita_misura
           FROM tpo.righe_ordine ro
           JOIN tpo.varieta v ON v.id = ro.varieta_id
           WHERE ro.ordine_id=%s ORDER BY ro.id""",
        (ord_id,),
    )
    for r in cur.fetchall():
        print(f"    riga {r[0]} v={r[1]} varieta={r[2]} qty={r[3]} uom={r[4]}")

cur.close()
conn.close()
