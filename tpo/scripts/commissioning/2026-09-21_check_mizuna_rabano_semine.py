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
            """SELECT v.public_id, v.denominazione, s.public_id, s.codice_tracciabilita,
                      s.stato, s.version, s.quantita_seme, s.unita_misura, s.data_avvio,
                      s.causa_origine, l.public_id, pv.public_id
               FROM tpo.semine s
               JOIN tpo.varieta v ON v.id = s.varieta_id
               JOIN tpo.lotti_seme l ON l.id = s.lotto_seme_id
               JOIN tpo.protocollo_versioni pv ON pv.id = s.protocollo_versione_id
               WHERE v.public_id IN ('VAR-000002', 'VAR-000004')
               ORDER BY v.public_id, s.data_avvio""",
        )
        rows = cur.fetchall()
        if not rows:
            print("NESSUNA SEMINA trovata per Rábano (VAR-000002) o Mizuna (VAR-000004).")
        for row in rows:
            (var_pid, var_nome, sem_pid, codice, stato, version, qta, uom,
             avvio, causa, lotto_pid, pv_pid) = row
            print(
                f"{var_nome} ({var_pid}) -> {sem_pid} / {codice}: stato={stato} "
                f"version={version} avvio={avvio} qta={qta}{uom.lower()} "
                f"causa={causa} lotto_seme={lotto_pid} protocollo={pv_pid}"
            )
finally:
    conn.close()
