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
        "Dettaglio ORD-000009/000010/000014 (stato, versione, date)",
        "SELECT public_id, stato, tipo_creazione, data_ordine, data_consegna_prevista, version "
        "FROM tpo.ordini WHERE public_id IN ('ORD-000009','ORD-000010','ORD-000014')",
    )
    run(
        "RIGHE di ORD-000009/000010/000014",
        "SELECT o.public_id AS ordine, ro.public_id AS riga, ro.posizione, v.codice_tracciabilita, "
        "ro.quantita, ro.unita_misura, ro.version "
        "FROM tpo.righe_ordine ro JOIN tpo.ordini o ON o.id=ro.ordine_id JOIN tpo.varieta v ON v.id=ro.varieta_id "
        "WHERE o.public_id IN ('ORD-000009','ORD-000010','ORD-000014') ORDER BY o.public_id, ro.posizione",
    )
    run(
        "Consegne gia' registrate su queste righe (se ce ne sono)",
        "SELECT ro.public_id AS riga, cn.public_id AS consegna, cn.stato "
        "FROM tpo.righe_ordine ro JOIN tpo.ordini o ON o.id=ro.ordine_id "
        "LEFT JOIN tpo.righe_consegna rc ON rc.riga_ordine_id = ro.id "
        "LEFT JOIN tpo.consegne cn ON cn.id = rc.consegna_id "
        "WHERE o.public_id IN ('ORD-000009','ORD-000010','ORD-000014')",
    )
finally:
    conn.close()
