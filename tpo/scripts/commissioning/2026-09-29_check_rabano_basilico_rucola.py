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
        "SEMINE non chiuse di Rabano (RAB) / Basilico (ALB) / Rucola (RUC), per codice esatto",
        "SELECT v.denominazione, s.public_id, s.codice_tracciabilita, s.stato, s.version, "
        "s.data_avvio, s.quantita_seme, s.unita_misura, s.lotto_seme_id "
        "FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id "
        "WHERE v.codice_tracciabilita IN ('RAB','ALB','RUC') AND s.stato <> 'CHIUSA' "
        "ORDER BY v.codice_tracciabilita, s.data_avvio DESC",
    )
    run(
        "TUTTE le semine di Rabano/Basilico/Rucola, qualunque stato (per contesto)",
        "SELECT v.denominazione, s.public_id, s.codice_tracciabilita, s.stato, s.data_avvio, "
        "s.quantita_seme, s.unita_misura "
        "FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id "
        "WHERE v.codice_tracciabilita IN ('RAB','ALB','RUC') "
        "ORDER BY v.codice_tracciabilita, s.data_avvio DESC",
    )
    run(
        "LOTTI SEME disponibili per Rabano/Basilico/Rucola",
        "SELECT v.codice_tracciabilita, ls.public_id, s.fornitore, s.referenza_commerciale, "
        "ls.quantita_residua, ls.unita_misura, ls.anomalia "
        "FROM tpo.lotti_seme ls "
        "JOIN tpo.sementi s ON s.id = ls.semente_id "
        "JOIN tpo.semente_impieghi si ON si.semente_id = s.id "
        "JOIN tpo.cultivar_usi cu ON cu.id = si.cultivar_uso_id "
        "JOIN tpo.cultivar c ON c.id = cu.cultivar_id "
        "JOIN tpo.varieta v ON v.id = c.varieta_id "
        "WHERE v.codice_tracciabilita IN ('RAB','ALB','RUC')",
    )
finally:
    conn.close()
