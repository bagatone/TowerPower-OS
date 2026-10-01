"""Diagnostica di sola lettura: verifica se PV-000005 e PV-000008 (Hinojo)
sono davvero due versioni valide contemporaneamente o se una copre gia'
una finestra di validita' chiusa -- prima di dire qualunque cosa a
Matteo su questo, controlliamo i dati veri invece di dedurli."""
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
            """SELECT pv.id, pv.public_id, pv.protocollo_id, pv.numero_versione,
                      pv.versione_precedente_id, pv.stato_approvazione,
                      pv.valida_dal, pv.valida_al, pv.created_at, pv.created_by,
                      p.id, p.denominazione, p.attivo, p.cultivar_uso_id
               FROM tpo.protocollo_versioni pv
               JOIN tpo.protocolli p ON p.id = pv.protocollo_id
               JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id
               JOIN tpo.cultivar c ON c.id = cu.cultivar_id
               JOIN tpo.varieta v ON v.id = c.varieta_id
               WHERE v.denominazione = 'Hinojo'
               ORDER BY pv.id"""
        )
        for row in cur.fetchall():
            print(row)
finally:
    conn.close()
