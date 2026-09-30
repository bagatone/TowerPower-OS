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
        "Consegne gia' registrate sulle righe Abaluus (RO-000001..4)",
        """SELECT ro.public_id AS riga, cn.public_id AS consegna, cn.stato
           FROM tpo.righe_ordine ro
           LEFT JOIN tpo.righe_consegna rc ON rc.riga_ordine_id = ro.id
           LEFT JOIN tpo.consegne cn ON cn.id = rc.consegna_id
           WHERE ro.public_id IN ('RO-000001','RO-000002','RO-000003','RO-000004')""",
    )
    run(
        "Consegne gia' registrate sulle righe Selvaje (RO-000015..18)",
        """SELECT ro.public_id AS riga, cn.public_id AS consegna, cn.stato
           FROM tpo.righe_ordine ro
           LEFT JOIN tpo.righe_consegna rc ON rc.riga_ordine_id = ro.id
           LEFT JOIN tpo.consegne cn ON cn.id = rc.consegna_id
           WHERE ro.public_id IN ('RO-000015','RO-000016','RO-000017','RO-000018')""",
    )
    run(
        "SEMINE Rabano non chiuse (stato attuale)",
        """SELECT v.denominazione, s.public_id, s.codice_tracciabilita, s.stato, s.version, s.data_avvio
           FROM tpo.semine s
           JOIN tpo.varieta v ON v.id = s.varieta_id
           WHERE v.public_id = 'VAR-000002' AND s.stato <> 'CHIUSA'
           ORDER BY s.data_avvio""",
    )
    run(
        "SEMINE Basilico/Albahaca non chiuse (stato attuale)",
        """SELECT v.denominazione, s.public_id, s.codice_tracciabilita, s.stato, s.version, s.data_avvio
           FROM tpo.semine s
           JOIN tpo.varieta v ON v.id = s.varieta_id
           WHERE v.public_id = 'VAR-000006' AND s.stato <> 'CHIUSA'
           ORDER BY s.data_avvio""",
    )
    run(
        "RACCOLTE mai registrate per Rabano o Basilico",
        """SELECT v.denominazione, r.public_id, r.quantita, r.unita_misura, r.effective_at
           FROM tpo.raccolte r
           JOIN tpo.semine s ON s.id = r.semina_id
           JOIN tpo.varieta v ON v.id = s.varieta_id
           WHERE v.public_id IN ('VAR-000002','VAR-000006')""",
    )
finally:
    conn.close()
