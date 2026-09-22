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

CLIENTI_PATTERNS = [("El Callao", "%callao%"), ("Azul y Sal", "%azul%sal%")]

try:
    for label, pat in CLIENTI_PATTERNS:
        run(f"CLIENTE {label}", "SELECT public_id, denominazione FROM tpo.clienti WHERE denominazione ILIKE %s", (pat,))
        run(
            f"ORDINI recenti per {label} (ultimi 21 giorni)",
            "SELECT o.public_id, o.stato, o.tipo_creazione, o.data_ordine, o.data_consegna_prevista, "
            "o.version, o.created_at "
            "FROM tpo.ordini o JOIN tpo.clienti c ON c.id = o.cliente_id "
            "WHERE c.denominazione ILIKE %s AND o.created_at >= now() - interval '21 days' "
            "ORDER BY o.created_at DESC",
            (pat,),
        )
        run(
            f"RIGHE_ORDINE recenti per {label}",
            "SELECT o.public_id AS ordine, ro.public_id AS riga, ro.posizione, v.codice_tracciabilita, "
            "ro.quantita, ro.unita_misura, ro.version "
            "FROM tpo.righe_ordine ro JOIN tpo.ordini o ON o.id = ro.ordine_id "
            "JOIN tpo.clienti c ON c.id = o.cliente_id JOIN tpo.varieta v ON v.id = ro.varieta_id "
            "WHERE c.denominazione ILIKE %s AND o.created_at >= now() - interval '21 days' "
            "ORDER BY o.created_at DESC",
            (pat,),
        )
        run(
            f"CONSEGNE recenti per {label}",
            "SELECT cn.public_id, cn.stato, cn.data_prevista, cn.data_effettiva "
            "FROM tpo.consegne cn JOIN tpo.clienti c ON c.id = cn.cliente_id "
            "WHERE c.denominazione ILIKE %s ORDER BY cn.data_prevista DESC LIMIT 10",
            (pat,),
        )

    run(
        "STOCK attuale Afila/Cilantro",
        "SELECT v.public_id, v.denominazione, s.disponibile, s.unita_misura, s.updated_at, s.version "
        "FROM tpo.stock s JOIN tpo.varieta v ON v.id = s.varieta_id "
        "WHERE v.codice_tracciabilita IN ('AFI','CIL')",
    )
    run(
        "RACCOLTE recenti Afila/Cilantro (cosa e' 'pronto')",
        "SELECT r.public_id, v.codice_tracciabilita, r.quantita, r.unita_misura, r.data_raccolta, "
        "r.destinazione_prevista "
        "FROM tpo.raccolte r JOIN tpo.semine s ON s.id = r.semina_id JOIN tpo.varieta v ON v.id = s.varieta_id "
        "WHERE v.codice_tracciabilita IN ('AFI','CIL') ORDER BY r.data_raccolta DESC LIMIT 20",
    )
finally:
    conn.close()
