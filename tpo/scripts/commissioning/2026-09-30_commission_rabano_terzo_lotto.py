"""Commissiona la semina RABANO del 26/9/2026 (sabato mattina, ore 9:00),
3 SET (42g a 14g/set, protocollo PV-000002), lotto seme LSE-000010
(Golinucci Organic), mai registrata prima nel sistema nonostante fosse
gia' stata confermata a voce in chat -- root cause non diagnosticata qui,
solo colmato il gap. Poi la porta attraverso il ciclo di vita fino a LUCE
(AVVIATA -> GERMINAZIONE amministrativa -> LUCE, quest'ultima riportata
da Matteo il 30/9/2026 ore 9:00, stesso schema gia' usato per Mizuna/
Rabano/Amaranto/Cilantro nel Fatto 27).

Idempotente: se una semina RABANO con data_avvio 2026-09-26 esiste gia',
salta la commissione e riparte dal suo stato reale per le transizioni.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python scripts/commissioning/2026-09-30_commission_rabano_terzo_lotto.py
"""
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

TZ = timezone(timedelta(hours=1))
RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
ORDER = ["AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA", "CHIUSA"]

AVVIO_AT = datetime(2026, 9, 26, 9, 0, 0, tzinfo=TZ)
LUCE_AT = datetime(2026, 9, 30, 9, 0, 0, tzinfo=TZ)


def db():
    p = load_postgresql_parameters()
    return psycopg.connect(
        host=p["host"], port=p["port"], dbname=p["dbname"],
        user=p["user"], password=p["password"], sslmode=p["sslmode"],
        connect_timeout=p["connect_timeout"],
    )


def run_cmd(cmd, label):
    print(f"--- {label} ---")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"FALLITO: {label}")
    return result.stdout


conn = db()
try:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.public_id, s.stato, s.version "
            "FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id "
            "WHERE v.codice_tracciabilita = 'RAB' AND s.data_avvio::date = '2026-09-26'"
        )
        existing = cur.fetchall()
finally:
    conn.close()

if existing:
    sem_pid, stato, version = existing[0]
    print(f"Semina Rabano del 26/9 gia' commissionata: {sem_pid} ({stato}, v{version}). Salto la commissione.")
else:
    conn = db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM tpo.lotti_seme WHERE public_id = 'LSE-000010'")
            (lse_version,) = cur.fetchone()
    finally:
        conn.close()
    print(f"LSE-000010 versione attesa: {lse_version}")

    out = run_cmd([
        RUN, "semina", "commission",
        "--seed-lot", "LSE-000010",
        "--expected-seed-lot-version", str(lse_version),
        "--protocol-version", "PV-000002",
        "--actual-seed-grams", "42",
        "--physical-started-at", AVVIO_AT.isoformat(),
        "--origin", "RIPRISTINO_STOCK",
        "--provenance", '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}',
        "--actor", "matteo",
        "--reason", "semina reale rabano 3 set di sabato 26/9 ore 9, mai registrata nel sistema nonostante conferma in chat; commissionata ora con i dati reali forniti da Matteo il 30/9",
        "--correlation-id", "SEMINA-2026-09-26-RABANO",
        "--idempotency-key", "semina-lse-000010-2026-09-26",
        "--confirm",
    ], "commissiona semina Rabano 26/9 (3 SET, 42g, LSE-000010)")
    sem_pid = None
    for line in out.splitlines():
        if line.startswith("PUBLIC_ID:"):
            sem_pid = line.split(":", 1)[1].strip()
    if not sem_pid:
        raise SystemExit("Non ho trovato PUBLIC_ID nell'output del commissioning. Fermo qui.")
    print(f"Nuova semina: {sem_pid}")

    conn = db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT stato, version FROM tpo.semine WHERE public_id = %s", (sem_pid,))
            stato, version = cur.fetchone()
    finally:
        conn.close()

print(f"Stato attuale {sem_pid}: {stato} (v{version})")
idx = ORDER.index(stato)
luce_idx = ORDER.index("LUCE")
if idx >= luce_idx:
    print(f"{sem_pid}: gia' a {stato} o oltre, nessuna transizione necessaria.")
    raise SystemExit(0)

current_version = version
step_effective_at = AVVIO_AT + timedelta(seconds=5)
for step_state in ORDER[idx + 1:luce_idx + 1]:
    if step_state == "LUCE":
        step_effective_at = LUCE_AT
        reason = (
            f"Transizione a LUCE per Rabano ({sem_pid}), riportata da Matteo "
            f"il 30/9/2026 (passata a luce stamattina, ore 9)."
        )
    else:
        reason = (
            f"Transizione amministrativa {step_state} (mai registrata finora) per "
            f"allineare Rabano ({sem_pid}) allo stato fisico reale, passo necessario "
            f"prima della transizione a LUCE riportata da Matteo il 30/9/2026."
        )
    idem = f"lifecycle-{sem_pid.lower()}-{step_state.lower()}-2026-09-30"
    corr = f"SEMINA-LIFECYCLE-2026-09-30-RABANO-{step_state}"
    cmd = [
        RUN, "semina", "transition",
        "--semina", sem_pid,
        "--expected-semina-version", str(current_version),
        "--target-state", step_state,
        "--effective-at", step_effective_at.isoformat(),
        "--provenance", '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED"}',
        "--actor", "matteo",
        "--reason", reason,
        "--correlation-id", corr,
        "--idempotency-key", idem,
        "--confirm",
    ]
    run_cmd(cmd, f"{sem_pid}: transizione a {step_state} (effective_at={step_effective_at.isoformat()})")
    current_version += 1
    step_effective_at = step_effective_at + timedelta(seconds=5)

print(f"=== FATTO: {sem_pid} ora a LUCE ===")
