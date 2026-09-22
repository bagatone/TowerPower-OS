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
cur = conn.cursor()

for sem_pid in ("SEM-000002", "SEM-000001"):
    cur.execute(
        """SELECT s.public_id, s.stato, s.version, s.data_avvio,
                  pv.public_id, v.denominazione
           FROM tpo.semine s
           JOIN tpo.protocollo_versioni pv ON pv.id = s.protocollo_versione_id
           JOIN tpo.varieta v ON v.id = s.varieta_id
           WHERE s.public_id=%s""",
        (sem_pid,),
    )
    row = cur.fetchone()
    print(f"{sem_pid}: stato={row[1]} version={row[2]} physical_started_at={row[3]} protocollo={row[4]} varieta={row[5]}")

for pv_pid in ("PV-000001", "PV-000003"):
    cur.execute(
        """SELECT public_id, idratazione_ore, germinazione_giorni, crescita_luce_giorni,
                  orario_semina_previsto, orario_raccolta_target, harvest_min_lead_giorni,
                  harvest_max_lead_giorni, buffer_temporale_minuti
           FROM tpo.protocollo_versioni WHERE public_id=%s""",
        (pv_pid,),
    )
    r = cur.fetchone()
    print(f"{pv_pid}: idratazione_ore={r[1]} germinazione_giorni={r[2]} crescita_luce_giorni={r[3]} "
          f"orario_semina={r[4]} orario_raccolta={r[5]} harvest_lead_min={r[6]} harvest_lead_max={r[7]} "
          f"buffer_min={r[8]}")

cur.close()
conn.close()
