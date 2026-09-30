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
        "VARIETA Afila",
        "SELECT id, public_id, denominazione, codice_tracciabilita, stato FROM tpo.varieta "
        "WHERE denominazione ILIKE %s OR codice_tracciabilita='AFI'",
        ("%afila%",),
    )
    run(
        "TUTTE le SEMINE di Afila (qualunque stato), piu' recenti prima",
        "SELECT s.public_id, s.codice_tracciabilita, s.stato, s.version, s.data_avvio, "
        "s.quantita_seme, s.unita_misura, s.lotto_seme_id, s.causa_origine "
        "FROM tpo.semine s "
        "JOIN tpo.varieta v ON v.id=s.varieta_id "
        "WHERE v.codice_tracciabilita='AFI' OR v.denominazione ILIKE %s "
        "ORDER BY s.data_avvio DESC",
        ("%afila%",),
    )
    run(
        "LOTTI SEME di Afila (fornitore, residuo, anomalia)",
        "SELECT ls.public_id, s.fornitore, s.referenza_commerciale, ls.quantita_residua, "
        "ls.unita_misura, ls.anomalia, ls.version "
        "FROM tpo.lotti_seme ls "
        "JOIN tpo.sementi s ON s.id=ls.semente_id "
        "JOIN tpo.cultivar_usi cu ON cu.id=(SELECT si.cultivar_uso_id FROM tpo.semente_impieghi si WHERE si.semente_id=s.id LIMIT 1) "
        "JOIN tpo.cultivar c ON c.id=cu.cultivar_id "
        "JOIN tpo.varieta v ON v.id=c.varieta_id "
        "WHERE v.codice_tracciabilita='AFI' OR v.denominazione ILIKE %s",
        ("%afila%",),
    )
    run(
        "Ultimi 30 eventi audit su semine di Afila (transizioni/commissioning)",
        "SELECT ae.occurred_at, ae.entity_type, ae.operation, ae.entity_public_id, ae.actor, ae.reason "
        "FROM tpo.audit_eventi ae "
        "WHERE ae.entity_public_id IN (SELECT s.public_id FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id WHERE v.codice_tracciabilita='AFI' OR v.denominazione ILIKE %s) "
        "ORDER BY ae.occurred_at DESC LIMIT 30",
        ("%afila%",),
    )
finally:
    conn.close()
