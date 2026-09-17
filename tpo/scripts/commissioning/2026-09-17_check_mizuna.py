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
        "VARIETA Mizuna",
        "SELECT public_id, denominazione, codice_tracciabilita, stato FROM tpo.varieta "
        "WHERE denominazione ILIKE %s OR codice_tracciabilita='MIZ'",
        ("%mizuna%",),
    )
    run(
        "LOTTO SEME LSE-000001",
        "SELECT ls.public_id, s.fornitore, s.referenza_commerciale, ls.quantita_residua, "
        "ls.unita_misura, ls.anomalia, ls.version "
        "FROM tpo.lotti_seme ls JOIN tpo.sementi s ON s.id=ls.semente_id "
        "WHERE ls.public_id='LSE-000001'",
    )
    run(
        "SEMENTE_IMPIEGHI collegati a Mizuna",
        "SELECT si.id, si.semente_id, si.cultivar_uso_id, si.raccomandazione, si.rating, si.motivazione "
        "FROM tpo.semente_impieghi si "
        "JOIN tpo.cultivar_usi cu ON cu.id=si.cultivar_uso_id "
        "JOIN tpo.cultivar c ON c.id=cu.cultivar_id "
        "JOIN tpo.varieta v ON v.id=c.varieta_id "
        "WHERE v.codice_tracciabilita='MIZ' OR v.denominazione ILIKE %s",
        ("%mizuna%",),
    )
    run(
        "PROTOCOLLO_VERSIONI collegati a Mizuna (ogni versione, non solo corrente)",
        "SELECT pv.public_id, pv.numero_versione, pv.valida_dal, pv.valida_al, pv.stato_approvazione, "
        "pv.idratazione_ore, pv.germinazione_giorni, pv.crescita_luce_giorni, pv.grammi_seme_per_set, "
        "pv.resa_attesa, pv.resa_unita_misura, pv.granularita_produttiva, "
        "pv.harvest_min_lead_giorni, pv.harvest_max_lead_giorni, pv.buffer_temporale_minuti "
        "FROM tpo.protocollo_versioni pv "
        "JOIN tpo.protocolli p ON p.id=pv.protocollo_id "
        "JOIN tpo.cultivar_usi cu ON cu.id=p.cultivar_uso_id "
        "JOIN tpo.cultivar c ON c.id=cu.cultivar_id "
        "JOIN tpo.varieta v ON v.id=c.varieta_id "
        "WHERE v.codice_tracciabilita='MIZ' OR v.denominazione ILIKE %s "
        "ORDER BY pv.valida_dal DESC",
        ("%mizuna%",),
    )
    run(
        "SEMINE gia' esistenti sul lotto LSE-000001",
        "SELECT public_id, codice_tracciabilita, stato, data_avvio, quantita_seme, unita_misura "
        "FROM tpo.semine WHERE lotto_seme_id=(SELECT id FROM tpo.lotti_seme WHERE public_id='LSE-000001')",
    )
finally:
    conn.close()
