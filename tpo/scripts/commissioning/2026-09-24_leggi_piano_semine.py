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
            """SELECT rps.public_id, rps.varieta_public_id_snapshot,
                      rps.quantita_produttiva_autorizzata, rps.unita_domanda,
                      rps.grammi_seme_richiesti, rps.sowing_at, rps.data_consegna,
                      rps.stato, c.denominazione, o.public_id
               FROM tpo.righe_piano_semina rps
               JOIN tpo.piano_produzione_revisioni pv ON pv.id = rps.piano_revisione_id
               JOIN tpo.righe_ordine ro ON ro.id = rps.riga_ordine_id
               JOIN tpo.ordini o ON o.id = ro.ordine_id
               JOIN tpo.clienti c ON c.id = o.cliente_id
               WHERE pv.public_id = 'RVP-000003'
               ORDER BY rps.sowing_at, rps.varieta_public_id_snapshot""",
        )
        rows = cur.fetchall()
        print(f"{len(rows)} righe nel piano RVP-000003\n")
        da_seminare = [r for r in rows if r[2] and r[2] > 0]
        print(f"=== Righe con NUOVA PRODUZIONE richiesta (quantita > 0): {len(da_seminare)} ===")
        for r in da_seminare:
            (rps_pid, varieta, qta, uom, grammi, sowing_at, consegna, stato, cliente, ord_pid) = r
            print(
                f"{varieta}: semina {qta}{uom.lower()} ({grammi}g seme) il {sowing_at:%Y-%m-%d %H:%M} "
                f"-> consegna {consegna} a {cliente} ({ord_pid}) [{rps_pid}, stato={stato}]"
            )
        coperte = [r for r in rows if not (r[2] and r[2] > 0)]
        print(f"\n=== Righe GIA' COPERTE da stock/produzione esistente (nessuna nuova semina): {len(coperte)} ===")
        for r in coperte:
            print(f"{r[1]} -> consegna {r[6]} a {r[8]} ({r[9]}) [{r[0]}]")
finally:
    conn.close()
