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
        cur.execute("""
            SELECT v.public_id, v.denominazione, c.id, c.denominazione, cu.id, cu.stato_validazione,
                   p.id, p.denominazione, p.tipo, p.attivo,
                   pv.public_id, pv.numero_versione, pv.stato_approvazione,
                   pv.idratazione_ore, pv.orario_semina_previsto, pv.orario_raccolta_target,
                   pv.germinazione_giorni, pv.crescita_luce_giorni, pv.ciclo_produttivo_nominale_giorni,
                   pv.grammi_seme_per_set, pv.resa_attesa, pv.resa_unita_misura,
                   pv.granularita_produttiva, pv.harvest_min_lead_giorni, pv.harvest_max_lead_giorni,
                   pv.buffer_temporale_minuti, pv.contenuto, pv.motivazione, pv.evidenze, pv.provenance
            FROM tpo.varieta v
            JOIN tpo.cultivar c ON c.varieta_id=v.id
            JOIN tpo.cultivar_usi cu ON cu.cultivar_id=c.id
            JOIN tpo.protocolli p ON p.cultivar_uso_id=cu.id
            JOIN tpo.protocollo_versioni pv ON pv.protocollo_id=p.id
            WHERE v.public_id='VAR-000003'
        """)
        cols = [d.name for d in cur.description]
        row = cur.fetchone()
        for name, value in zip(cols, row):
            print(f"{name}: {value!r}")
finally:
    conn.close()
