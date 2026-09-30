"""Commissiona la terza semina Afila reale (6 SET, messi in idratazione
ieri 28/9 e seminati oggi 29/9 alle 9:00, lotto LSE-000014 Golinucci --
stesso gia' usato per SEM-000002 e SEM-000010). Nessuna transizione di
stadio richiesta: e' stata seminata oggi stesso, resta AVVIATA.

Idempotente: controlla prima se esiste gia' una semina su questo lotto
con questa data di avvio, e salta se trovata. Legge la versione del
lotto seme dal vivo un istante prima del commissioning.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python scripts/commissioning/2026-09-29_commission_afila_terzo_lotto.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
LSE = "LSE-000014"
PHYSICAL_STARTED_AT = "2026-09-29T09:00:00+01:00"
SET_QUANTITY = 6


def run_cli(cmd, label):
    print(f"--- {label} ---")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"FALLITO: {label}")
    return result.stdout


parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
with conn.cursor() as cur:
    cur.execute(
        """SELECT pv.public_id, pv.grammi_seme_per_set FROM tpo.protocollo_versioni pv
           JOIN tpo.protocolli p ON p.id = pv.protocollo_id
           JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id
           JOIN tpo.cultivar c ON c.id = cu.cultivar_id
           JOIN tpo.varieta v ON v.id = c.varieta_id
           WHERE v.codice_tracciabilita = 'AFI' AND pv.valida_al IS NULL
           ORDER BY pv.numero_versione DESC LIMIT 1"""
    )
    pv_public_id, grammi_per_set = cur.fetchone()
    print(f"Protocollo Afila corrente: {pv_public_id} grammi_per_set={grammi_per_set}")

    cur.execute(
        """SELECT s.public_id, s.stato FROM tpo.semine s
           JOIN tpo.lotti_seme l ON l.id = s.lotto_seme_id
           WHERE l.public_id = %s AND s.data_avvio = %s""",
        (LSE, PHYSICAL_STARTED_AT),
    )
    already = cur.fetchone()
conn.close()

if already:
    print(f"Semina gia' registrata: {already} -- non commissiono di nuovo.")
    raise SystemExit(0)

grammi = int(grammi_per_set) * SET_QUANTITY
print(f"Da commissionare: {SET_QUANTITY} SET x {grammi_per_set}g = {grammi}g")

conn2 = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
with conn2.cursor() as cur:
    cur.execute("SELECT version FROM tpo.lotti_seme WHERE public_id=%s", (LSE,))
    seed_lot_version = cur.fetchone()[0]
conn2.close()

run_cli([
    RUN, "semina", "commission",
    "--seed-lot", LSE,
    "--expected-seed-lot-version", str(seed_lot_version),
    "--protocol-version", pv_public_id,
    "--actual-seed-grams", str(grammi),
    "--physical-started-at", PHYSICAL_STARTED_AT,
    "--origin", "RIPRISTINO_STOCK",
    "--provenance", '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED",'
                    '"selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}',
    "--actor", "matteo",
    "--reason", "semina reale afila (terzo lotto) del 29/9 ore 9:00, messo in idratazione il "
                "28/9, registrata in giornata",
    "--correlation-id", "SEMINA-2026-09-29-AFILA-3",
    "--idempotency-key", "semina-lse-000014-2026-09-29",
    "--confirm",
], "semina Afila (terzo lotto, 6 SET)")

print("=== FATTO ===")
