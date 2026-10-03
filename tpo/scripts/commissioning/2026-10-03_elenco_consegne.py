"""Diagnostica di SOLA LETTURA: elenca le CONSEGNE con cliente, data, stato,
numero di righe e quantita' spiegata dal registro lotti (CONSUMO_LOTTO).
Serve a trovare il CON-###### da passare a `tpo bolla genera`."""
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
    connect_timeout=parameters["connect_timeout"], autocommit=True,
)
try:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT c.public_id, cl.denominazione, c.stato::text,
                   COALESCE(c.data_effettiva::date, c.data_prevista) AS data,
                   COUNT(rc.id) AS righe,
                   COALESCE(SUM(rc.quantita), 0) AS quantita,
                   COALESCE(SUM(l.q), 0) AS spiegata
            FROM tpo.consegne c
            JOIN tpo.clienti cl ON cl.id = c.cliente_id
            LEFT JOIN tpo.righe_consegna rc ON rc.consegna_id = c.id
            LEFT JOIN (
                SELECT ms.riga_consegna_id, SUM(k.quantita) AS q
                FROM tpo.movimenti_magazzino ms
                JOIN tpo.consumi_lotto k ON k.movimento_scarico_id = ms.id
                GROUP BY ms.riga_consegna_id
            ) l ON l.riga_consegna_id = rc.id
            GROUP BY c.public_id, cl.denominazione, c.stato, c.data_effettiva, c.data_prevista
            ORDER BY c.public_id""")
        print("consegna | cliente | stato | data | righe | quantita | spiegata dai lotti")
        for row in cur.fetchall():
            print(" | ".join(str(x) for x in row))
finally:
    conn.close()
