"""Diagnostica di sola lettura, seguito a 2026-10-01_check_versioni_
programma_fornitura.py: l'indice unico uq_programmi_fornitura_versioni_
corrente esclude le righe con voided_at NOT NULL -- quindi avere 2 righe
con valida_al IS NULL per lo stesso programma NON e' di per se' un bug
se una delle due e' voided_at NOT NULL (stesso tipo di falso allarme gia'
verificato per Hinojo il 19/9: prima di dire che e' un bug, controlliamo
voided_at/replacement_version_id per tutti i 9 programmi coinvolti)."""
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
        cur.execute(
            """SELECT pf.public_id, pfv.numero_versione, pfv.stato,
                      pfv.valida_dal, pfv.valida_al, pfv.voided_at,
                      pfv.replacement_version_id, pfv.id, pfv.created_at, pfv.created_by
               FROM tpo.programmi_fornitura_versioni pfv
               JOIN tpo.programmi_fornitura pf ON pf.id = pfv.programma_fornitura_id
               WHERE pfv.valida_al IS NULL
               ORDER BY pf.public_id, pfv.numero_versione"""
        )
        for row in cur.fetchall():
            print(row)
finally:
    conn.close()
