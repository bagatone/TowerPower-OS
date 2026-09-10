"""Introspezione di sola lettura dello schema reale (evita di indovinare
i nomi delle colonne dalle migrazioni, che ha gia' causato due errori).

Uso: .venv/bin/python scripts/commissioning/2026-09-10_introspect_schema.py
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
tables = [
    "lotti_seme", "sementi", "semente_impieghi", "cultivar_usi",
    "cultivar", "varieta", "usi_produttivi", "protocolli", "protocollo_versioni",
]
try:
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='tpo' AND table_name=%s ORDER BY ordinal_position",
                (table,),
            )
            print(f"=== tpo.{table} ===")
            for col, dtype in cur.fetchall():
                print(f"  {col}  ({dtype})")
            print()
finally:
    conn.close()
