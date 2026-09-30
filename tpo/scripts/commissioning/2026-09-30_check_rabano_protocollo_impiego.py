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
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description] if cur.description else []
        print(cols)
        for row in cur.fetchall():
            print(row)
    print()
run("Protocollo Rabano APPROVATA",
    "SELECT pv.public_id, pv.numero_versione, pv.grammi_seme_per_set, pv.idratazione_ore, "
    "pv.germinazione_giorni, pv.crescita_luce_giorni, pv.stato_approvazione "
    "FROM tpo.protocollo_versioni pv "
    "JOIN tpo.protocolli p ON p.id = pv.protocollo_id "
    "JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id "
    "JOIN tpo.cultivar c ON c.id = cu.cultivar_id "
    "JOIN tpo.varieta v ON v.id = c.varieta_id "
    "WHERE v.codice_tracciabilita = 'RAB' AND pv.stato_approvazione = 'APPROVATA'")
run("semente_impieghi esistente per Golinucci Rabano",
    "SELECT si.id, si.raccomandazione, si.rating, s.fornitore, s.referenza_commerciale "
    "FROM tpo.semente_impieghi si "
    "JOIN tpo.cultivar_usi cu ON cu.id = si.cultivar_uso_id "
    "JOIN tpo.sementi s ON s.id = si.semente_id "
    "JOIN tpo.cultivar c ON c.id = cu.cultivar_id "
    "JOIN tpo.varieta v ON v.id = c.varieta_id "
    "WHERE v.codice_tracciabilita = 'RAB' AND s.fornitore = 'Golinucci Organic'")
conn.close()
