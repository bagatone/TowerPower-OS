"""Diagnostica di sola lettura: lo script elenco_clienti_programmi.py ha
mostrato PIU' di una versione con valida_al IS NULL per lo stesso
programma_fornitura_id -- cosa che l'indice unico parziale
uq_programmi_fornitura_versioni_corrente dovrebbe rendere impossibile.
Qui guardiamo i dati grezzi (tutte le versioni di un programma, con
valida_al/valida_dal/created_at) e verifichiamo se quell'indice esiste
davvero sul database reale."""
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
        print("=== indici su tpo.programmi_fornitura_versioni ===")
        cur.execute(
            """SELECT indexname, indexdef FROM pg_indexes
               WHERE schemaname='tpo' AND tablename='programmi_fornitura_versioni'
               ORDER BY indexname"""
        )
        for row in cur.fetchall():
            print(row[0])
            print(f"    {row[1]}")

        print("\n=== tutte le versioni di PF-000001 (Abaluus) ===")
        cur.execute(
            """SELECT pfv.numero_versione, pfv.stato, pfv.valida_dal, pfv.valida_al,
                      pfv.created_at, pfv.created_by
               FROM tpo.programmi_fornitura_versioni pfv
               JOIN tpo.programmi_fornitura pf ON pf.id = pfv.programma_fornitura_id
               WHERE pf.public_id = 'PF-000001'
               ORDER BY pfv.numero_versione"""
        )
        for row in cur.fetchall():
            print(row)

        print("\n=== quante versioni con valida_al IS NULL, per programma ===")
        cur.execute(
            """SELECT pf.public_id, COUNT(*)
               FROM tpo.programmi_fornitura_versioni pfv
               JOIN tpo.programmi_fornitura pf ON pf.id = pfv.programma_fornitura_id
               WHERE pfv.valida_al IS NULL
               GROUP BY pf.public_id
               HAVING COUNT(*) > 1
               ORDER BY pf.public_id"""
        )
        for row in cur.fetchall():
            print(row)
finally:
    conn.close()
