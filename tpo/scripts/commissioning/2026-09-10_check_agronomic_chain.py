"""Diagnostica di sola lettura: quanto e' completa la catena agronomica
necessaria prima di poter commissionare una SEMINA reale
(varieta -> cultivar -> cultivar_usi -> protocolli -> protocollo_versioni,
+ semente_impieghi che collega le sementi ai cultivar_usi).

Uso: .venv/bin/python scripts/commissioning/2026-09-10_check_agronomic_chain.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402

import psycopg  # noqa: E402

parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
try:
    with conn.cursor() as cur:
        print("=== conteggio righe per tabella ===")
        for table in ("varieta", "cultivar", "cultivar_usi", "usi_produttivi",
                      "protocolli", "protocollo_versioni", "semente_impieghi", "sementi"):
            cur.execute(f"SELECT count(*) FROM tpo.{table}")
            print(f"  tpo.{table}: {cur.fetchone()[0]}")

        print()
        print("=== varieta esistenti (public_id, denominazione, stato) ===")
        cur.execute("SELECT public_id, denominazione, stato FROM tpo.varieta ORDER BY public_id")
        for row in cur.fetchall():
            print(" ", row)

        print()
        print("=== cultivar esistenti (varieta_id, denominazione, stato) ===")
        cur.execute("""
            SELECT v.public_id, c.denominazione, c.stato
            FROM tpo.cultivar c JOIN tpo.varieta v ON v.id = c.varieta_id
            ORDER BY v.public_id
        """)
        rows = cur.fetchall()
        if not rows:
            print("  (nessun cultivar registrato)")
        for row in rows:
            print(" ", row)
finally:
    conn.close()
