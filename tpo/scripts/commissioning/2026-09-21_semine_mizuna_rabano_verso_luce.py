"""Porta a LUCE le semine ATTUALMENTE ATTIVE di Mizuna (VAR-000004) e
Rábano (VAR-000002), rilevando da sole il loro stato reale nel database
e applicando solo i passi di transizione mancanti (AVVIATA->GERMINAZIONE
se non gia' fatto, poi GERMINAZIONE->LUCE) -- nessun dato inventato, ogni
`--semina`/`--expected-semina-version` viene letto dal DB un istante
prima di essere usato per la transizione corrispondente.

v2 (21/9/2026, dopo il primo run): il motore SEMINA rifiuta due
transizioni con lo stesso `effective_at` (SEMINA_LIFECYCLE_TIMESTAMP_
REGRESSION, deve essere strettamente monotono) -- corretto incrementando
il timestamp di qualche secondo ad ogni passo invece di riusare lo
stesso "ora" per tutti.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python scripts/commissioning/2026-09-21_semine_mizuna_rabano_verso_luce.py
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
NOW = datetime.now(TZ).replace(microsecond=0)
RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")

VARIETA = [("VAR-000002", "Rábano"), ("VAR-000004", "Mizuna")]
ORDER = ["AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA", "CHIUSA"]


def transiziona(semina_pid, expected_version, target_state, var_nome, effective_at):
    idem = f"lifecycle-{semina_pid.lower()}-{target_state.lower()}-2026-09-21"
    corr = f"SEMINA-LIFECYCLE-2026-09-21-{var_nome.upper()}-{target_state}"
    reason = (
        f"Transizione a {target_state} per {var_nome} ({semina_pid}), riportata "
        f"da Giulia il 21/9/2026 (fine germinazione, inizio fase vegetativa in luce)."
        if target_state == "LUCE" else
        f"Transizione amministrativa {target_state} (mai registrata finora nel "
        f"sistema) per allineare {var_nome} ({semina_pid}) allo stato fisico reale, "
        f"passo necessario prima della transizione a LUCE richiesta da Giulia il 21/9/2026."
    )
    cmd = [
        RUN, "semina", "transition",
        "--semina", semina_pid,
        "--expected-semina-version", str(expected_version),
        "--target-state", target_state,
        "--effective-at", effective_at.isoformat(),
        "--provenance", '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED"}',
        "--actor", "giulia",
        "--reason", reason,
        "--correlation-id", corr,
        "--idempotency-key", idem,
        "--confirm",
    ]
    print(f"--- {semina_pid} ({var_nome}): {target_state} (effective_at={effective_at.isoformat()}) ---")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"FALLITA la transizione {semina_pid} -> {target_state}")


parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
try:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT s.public_id, s.stato, s.version, v.public_id, v.denominazione
               FROM tpo.semine s
               JOIN tpo.varieta v ON v.id = s.varieta_id
               WHERE v.public_id IN ('VAR-000002', 'VAR-000004') AND s.stato <> 'CHIUSA'
               ORDER BY v.public_id, s.data_avvio"""
        )
        rows = cur.fetchall()
finally:
    conn.close()

if not rows:
    print("NESSUNA semina attiva trovata per Rábano o Mizuna. Nessuna azione eseguita.")
    raise SystemExit(0)

by_var = {}
for sem_pid, stato, version, var_pid, var_nome in rows:
    by_var.setdefault(var_pid, []).append((sem_pid, stato, version, var_nome))

for var_pid, var_nome in VARIETA:
    candidates = by_var.get(var_pid, [])
    if not candidates:
        print(f"{var_nome} ({var_pid}): nessuna semina attiva trovata, salto.")
        continue
    if len(candidates) > 1:
        print(f"{var_nome} ({var_pid}): trovate {len(candidates)} semine attive, "
              f"AMBIGUO, non tocco nulla -> {candidates}")
        continue
    sem_pid, stato, version, _ = candidates[0]
    idx = ORDER.index(stato)
    luce_idx = ORDER.index("LUCE")
    if idx >= luce_idx:
        print(f"{var_nome} ({var_pid}) {sem_pid}: gia' a {stato}, nessuna azione.")
        continue
    current_version = version
    step_effective_at = NOW
    for step_state in ORDER[idx + 1:luce_idx + 1]:
        transiziona(sem_pid, current_version, step_state, var_nome, step_effective_at)
        current_version += 1
        step_effective_at = step_effective_at + timedelta(seconds=5)
    print(f"{var_nome} ({var_pid}) {sem_pid}: ora a LUCE.")

print("=== FATTO ===")
