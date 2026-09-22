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
        "CLIENTE Salvaje/Selvaje",
        "SELECT public_id, denominazione FROM tpo.clienti WHERE denominazione ILIKE %s",
        ("%lvaje%",),
    )
    run(
        "ORDINI recenti per questo cliente (ultimi 21 giorni)",
        "SELECT o.public_id, o.stato, o.tipo_creazione, o.data_ordine, o.data_consegna_prevista, "
        "o.version, o.created_at "
        "FROM tpo.ordini o "
        "JOIN tpo.clienti c ON c.id = o.cliente_id "
        "WHERE c.denominazione ILIKE %s AND o.created_at >= now() - interval '21 days' "
        "ORDER BY o.created_at DESC",
        ("%lvaje%",),
    )
    run(
        "RIGHE_ORDINE di quegli ordini (varieta, quantita)",
        "SELECT o.public_id AS ordine, ro.public_id AS riga, ro.posizione, v.codice_tracciabilita, "
        "ro.quantita, ro.unita_misura, ro.version "
        "FROM tpo.righe_ordine ro "
        "JOIN tpo.ordini o ON o.id = ro.ordine_id "
        "JOIN tpo.clienti c ON c.id = o.cliente_id "
        "JOIN tpo.varieta v ON v.id = ro.varieta_id "
        "WHERE c.denominazione ILIKE %s AND o.created_at >= now() - interval '21 days' "
        "ORDER BY o.created_at DESC",
        ("%lvaje%",),
    )
    run(
        "RACCOLTE recenti (Afila/Cilantro), per capire cosa e' 'pronto'",
        "SELECT r.public_id, v.codice_tracciabilita, r.quantita, r.unita_misura, r.data_raccolta, "
        "r.destinazione_prevista "
        "FROM tpo.raccolte r "
        "JOIN tpo.semine s ON s.id = r.semina_id "
        "JOIN tpo.varieta v ON v.id = s.varieta_id "
        "WHERE v.codice_tracciabilita IN ('AFI','CIL') "
        "ORDER BY r.data_raccolta DESC LIMIT 20",
    )
    run(
        "CLIENTE La Puipana (verifica se gia' onboardato)",
        "SELECT public_id, denominazione FROM tpo.clienti WHERE denominazione ILIKE %s",
        ("%uipana%",),
    )
    run(
        "PROGRAMMA_FORNITURA attivo per Salvaje (per la sospensione)",
        "SELECT pf.public_id, pf.data_ripresa_prevista, pfv.numero_versione, pfv.stato, "
        "pfv.valida_dal, pfv.valida_al "
        "FROM tpo.programmi_fornitura pf "
        "JOIN tpo.programmi_fornitura_versioni pfv ON pfv.programma_fornitura_id = pf.id "
        "JOIN tpo.clienti c ON c.id = pf.cliente_id "
        "WHERE c.denominazione ILIKE %s AND pfv.valida_al IS NULL "
        "ORDER BY pfv.numero_versione DESC",
        ("%lvaje%",),
    )
    run(
        "CONSEGNE recenti per questo cliente (se ce ne sono gia')",
        "SELECT cn.public_id, cn.stato, cn.data_prevista, cn.data_effettiva "
        "FROM tpo.consegne cn "
        "JOIN tpo.clienti c ON c.id = cn.cliente_id "
        "WHERE c.denominazione ILIKE %s "
        "ORDER BY cn.data_prevista DESC LIMIT 10",
        ("%lvaje%",),
    )
finally:
    conn.close()
