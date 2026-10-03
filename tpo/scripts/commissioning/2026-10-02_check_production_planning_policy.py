"""Diagnostica di sola lettura: la policy di Production Planning corrente
(buffer quantitativo) e quante righe-ordine distinte per varieta' esistono
oggi nei programmi di fornitura correnti -- serve a capire l'effetto
reale di un buffer ABSOLUTE_SET, che si applica per riga-ordine (quindi
per singolo cliente), non per varieta' aggregata."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

p = load_postgresql_parameters()
conn = psycopg.connect(
    host=p["host"], port=p["port"], dbname=p["dbname"],
    user=p["user"], password=p["password"], sslmode=p["sslmode"],
    connect_timeout=p["connect_timeout"],
)
try:
    with conn.cursor() as cur:
        print("=== policy Production Planning correnti (valida_al IS NULL) ===")
        cur.execute(
            """SELECT policy_set_code, numero_versione, harvest_target_strategy,
                      buffer_quantitativo_tipo, buffer_quantitativo_valore,
                      priority_policy_code, planning_algorithm_version,
                      valida_dal, valida_al
               FROM tpo.production_planning_policy_versions
               ORDER BY policy_set_code, numero_versione"""
        )
        for row in cur.fetchall():
            print(row)

        print("\n=== righe attive per varieta' (quante righe-ordine distinte oggi) ===")
        cur.execute(
            """SELECT v.denominazione, COUNT(*)
               FROM tpo.righe_programma_fornitura rpf
               JOIN tpo.varieta v ON v.id = rpf.varieta_id
               JOIN tpo.programmi_fornitura_versioni pfv ON pfv.id = rpf.programma_versione_id
               WHERE pfv.valida_al IS NULL AND pfv.voided_at IS NULL AND pfv.stato = 'ATTIVO'
               GROUP BY v.denominazione ORDER BY COUNT(*) DESC"""
        )
        for row in cur.fetchall():
            print(row)
finally:
    conn.close()
