"""Sola lettura: version/anomalia/quantita per lotti seme specifici, serve
per preparare i comandi reali di 'tpo semina commission' (che richiedono
--expected-seed-lot-version, non esposto dalla API di sola lettura).
Uso:
  .venv/bin/python scripts/commissioning/2026-09-15_verifica_lotti.py LSE-000013 LSE-000014
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402

import psycopg  # noqa: E402

ids = sys.argv[1:]
if not ids:
    print("Uso: verifica_lotti.py LSE-000013 LSE-000014 ...")
    raise SystemExit(1)

parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
try:
    with conn.cursor() as cur:
        for lot_id in ids:
            cur.execute(
                """SELECT public_id, version, quantita_residua, data_scadenza, anomalia
                   FROM tpo.lotti_seme WHERE public_id=%s""",
                (lot_id,),
            )
            row = cur.fetchone()
            if not row:
                print(f"{lot_id}: NON TROVATO")
                continue
            pid, version, qty, scad, anomalia = row
            print(f"{pid}: version={version}  quantita_residua={qty}  data_scadenza={scad}")
            print(f"    anomalia={'NESSUNA' if anomalia is None else anomalia}")
finally:
    conn.close()
