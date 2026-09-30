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
        "Tutti i CLIENTI reali",
        "SELECT public_id, denominazione FROM tpo.clienti ORDER BY public_id",
    )
    run(
        "Tutte le VARIETA reali",
        "SELECT public_id, denominazione, codice_tracciabilita FROM tpo.varieta ORDER BY public_id",
    )
    run(
        "SEMINE Cilantro non chiuse (stato attuale)",
        """SELECT v.public_id, v.denominazione, s.public_id, s.codice_tracciabilita,
                  s.stato, s.version, s.data_avvio
           FROM tpo.semine s
           JOIN tpo.varieta v ON v.id = s.varieta_id
           WHERE v.denominazione ILIKE %s AND s.stato <> 'CHIUSA'
           ORDER BY s.data_avvio""",
        ("%cilantro%",),
    )
    run(
        "ORDINI di Abaluus (qualunque stato)",
        """SELECT o.public_id, o.stato, o.data_ordine, o.data_consegna_prevista, o.version
           FROM tpo.ordini o
           JOIN tpo.clienti c ON c.id = o.cliente_id
           WHERE c.denominazione ILIKE %s
           ORDER BY o.data_ordine""",
        ("%abaluus%",),
    )
    run(
        "RIGHE degli ordini di Abaluus",
        """SELECT o.public_id AS ordine, ro.public_id AS riga, v.denominazione,
                  ro.quantita, ro.unita_misura, ro.version
           FROM tpo.righe_ordine ro
           JOIN tpo.ordini o ON o.id = ro.ordine_id
           JOIN tpo.clienti c ON c.id = o.cliente_id
           JOIN tpo.varieta v ON v.id = ro.varieta_id
           WHERE c.denominazione ILIKE %s
           ORDER BY o.public_id, ro.posizione""",
        ("%abaluus%",),
    )
    run(
        "ORDINI di Selvaje (qualunque stato)",
        """SELECT o.public_id, o.stato, o.data_ordine, o.data_consegna_prevista, o.version
           FROM tpo.ordini o
           JOIN tpo.clienti c ON c.id = o.cliente_id
           WHERE c.denominazione ILIKE %s
           ORDER BY o.data_ordine""",
        ("%selvaje%",),
    )
    run(
        "RIGHE degli ordini di Selvaje",
        """SELECT o.public_id AS ordine, ro.public_id AS riga, v.denominazione,
                  ro.quantita, ro.unita_misura, ro.version
           FROM tpo.righe_ordine ro
           JOIN tpo.ordini o ON o.id = ro.ordine_id
           JOIN tpo.clienti c ON c.id = o.cliente_id
           JOIN tpo.varieta v ON v.id = ro.varieta_id
           WHERE c.denominazione ILIKE %s
           ORDER BY o.public_id, ro.posizione""",
        ("%selvaje%",),
    )
    run(
        "STOCK attuale per Afila, Rabano, Cilantro, Basilico(Albahaca)",
        """SELECT v.denominazione, s.unita_misura, s.disponibile
           FROM tpo.stock s
           JOIN tpo.varieta v ON v.id = s.varieta_id
           WHERE v.public_id IN ('VAR-000001','VAR-000002','VAR-000003','VAR-000006')
           ORDER BY v.denominazione""",
    )
finally:
    conn.close()
