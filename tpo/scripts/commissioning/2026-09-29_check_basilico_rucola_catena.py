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
        "CULTIVAR/CULTIVAR_USI di Basilico (ALB) e Rucola (RUC)",
        "SELECT v.codice_tracciabilita, c.id AS cultivar_id, c.denominazione, "
        "cu.id AS cultivar_uso_id, cu.uso_produttivo_snapshot "
        "FROM tpo.varieta v "
        "JOIN tpo.cultivar c ON c.varieta_id = v.id "
        "JOIN tpo.cultivar_usi cu ON cu.cultivar_id = c.id "
        "WHERE v.codice_tracciabilita IN ('ALB','RUC')",
    )
    run(
        "PROTOCOLLI/PROTOCOLLO_VERSIONI di Basilico e Rucola (qualunque stato)",
        "SELECT v.codice_tracciabilita, pv.public_id, pv.numero_versione, pv.stato_approvazione, "
        "pv.valida_dal, pv.valida_al, pv.grammi_seme_per_set, pv.germinazione_giorni, "
        "pv.crescita_luce_giorni "
        "FROM tpo.protocollo_versioni pv "
        "JOIN tpo.protocolli p ON p.id = pv.protocollo_id "
        "JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id "
        "JOIN tpo.cultivar c ON c.id = cu.cultivar_id "
        "JOIN tpo.varieta v ON v.id = c.varieta_id "
        "WHERE v.codice_tracciabilita IN ('ALB','RUC') "
        "ORDER BY v.codice_tracciabilita, pv.numero_versione",
    )
    run(
        "SEMENTI (lotti d'acquisto) collegati a cultivar Basilico/Rucola, via semente_impieghi",
        "SELECT v.codice_tracciabilita, s.id AS semente_id, s.fornitore, s.referenza_commerciale "
        "FROM tpo.sementi s "
        "JOIN tpo.semente_impieghi si ON si.semente_id = s.id "
        "JOIN tpo.cultivar_usi cu ON cu.id = si.cultivar_uso_id "
        "JOIN tpo.cultivar c ON c.id = cu.cultivar_id "
        "JOIN tpo.varieta v ON v.id = c.varieta_id "
        "WHERE v.codice_tracciabilita IN ('ALB','RUC')",
    )
    run(
        "TUTTI i lotti seme il cui fornitore/referenza menzioni basilico/albahaca/rucola/rocket (ricerca larga, testuale)",
        "SELECT ls.public_id, s.fornitore, s.referenza_commerciale, ls.quantita_residua, "
        "ls.unita_misura, ls.anomalia "
        "FROM tpo.lotti_seme ls JOIN tpo.sementi s ON s.id = ls.semente_id "
        "WHERE s.referenza_commerciale ILIKE %s OR s.referenza_commerciale ILIKE %s "
        "OR s.referenza_commerciale ILIKE %s OR s.referenza_commerciale ILIKE %s",
        ("%basil%", "%albahaca%", "%rucola%", "%rocket%"),
    )
finally:
    conn.close()
