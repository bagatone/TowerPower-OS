"""Diagnostica di sola lettura (nessuna scrittura): lo script precedente
(2026-10-01_check_duplicati_da_seminare.py) ha mostrato che quasi ogni riga
d'ordine compare due volte nel rendiconto, una sotto piano_revisione_id=1 e
una sotto piano_revisione_id=2 -- qui verifichiamo se sono davvero la STESSA
piano_produzione_id (e quindi la revisione 1 avrebbe dovuto essere segnata
come sostituita quando e' nata la 2, ma non lo e' stata) oppure due piani
distinti (nel qual caso non sarebbe affatto un bug)."""
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
try:
    with conn.cursor() as cur:
        print("=== tpo.piani_produzione ===")
        cur.execute(
            "SELECT id, public_id, current_revision_id FROM tpo.piani_produzione ORDER BY id"
        )
        for row in cur.fetchall():
            print(row)

        print("\n=== tpo.piano_produzione_revisioni (tutte) ===")
        cur.execute(
            """SELECT id, public_id, piano_produzione_id, numero_revisione,
                      revisione_precedente_id, sostituita_at, sostituita_by,
                      created_at, created_by, replanning_reason_code
               FROM tpo.piano_produzione_revisioni ORDER BY id"""
        )
        for row in cur.fetchall():
            print(row)

        print("\n=== quante righe_piano_semina per ciascuna revisione ===")
        cur.execute(
            """SELECT piano_revisione_id, COUNT(*), MIN(stato), MAX(stato)
               FROM tpo.righe_piano_semina GROUP BY piano_revisione_id ORDER BY piano_revisione_id"""
        )
        for row in cur.fetchall():
            print(row)
finally:
    conn.close()
