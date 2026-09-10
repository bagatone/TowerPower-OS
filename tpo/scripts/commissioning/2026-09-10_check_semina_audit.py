"""Diagnostica di sola lettura: perche' tpo.semine e' vuota?

Controlla se esistono tracce nell'audit trail di un tentativo di
commissioning SEMINA (correlation_id 'SEMINA-2026-09-07', usato dallo
script scripts/commissioning/2026-09-07_semina_commissioning.sh) e mostra
gli ultimi eventi registrati in generale, per capire se quel comando sia
mai arrivato al database reale.

Uso: .venv/bin/python scripts/commissioning/2026-09-10_check_semina_audit.py
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
        print("=== righe totali nelle tabelle SEMINA/LOTTO_SEME/RACCOLTA ===")
        for table in ("semine", "lotti_seme", "raccolte"):
            cur.execute(f"SELECT count(*) FROM tpo.{table}")
            print(f"  tpo.{table}: {cur.fetchone()[0]}")

        print()
        print("=== tentativi con correlation_id 'SEMINA-2026-09-07' (audit_eventi) ===")
        cur.execute(
            "SELECT entity_type, operation, entity_public_id, occurred_at "
            "FROM tpo.audit_eventi WHERE correlation_id = %s ORDER BY id",
            ("SEMINA-2026-09-07",),
        )
        rows = cur.fetchall()
        if not rows:
            print("  (nessuna traccia: il comando non e' mai arrivato al database reale)")
        for row in rows:
            print(" ", row)

        print()
        print("=== ultimi 10 eventi in audit_eventi (qualunque tipo) ===")
        cur.execute(
            "SELECT entity_type, operation, entity_public_id, occurred_at "
            "FROM tpo.audit_eventi ORDER BY occurred_at DESC LIMIT 10"
        )
        for row in cur.fetchall():
            print(" ", row)
finally:
    conn.close()
