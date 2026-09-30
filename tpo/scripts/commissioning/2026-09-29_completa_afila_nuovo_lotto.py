"""Commissiona la semina Afila reale del 20/9/2026 ore 9:00 (4 SET, lotto
LSE-000014 Golinucci Organic / Pea Green Affila -- lo stesso gia' usato
per SEM-000002), scoperta mancante il 29/9/2026 (nessuna seconda semina
Afila trovata, verificato con 2026-09-29_check_afila_semine.py) mentre
Matteo la credeva gia' registrata tramite il diario.

Poi applica le transizioni mancanti verso LUCE:
- GERMINAZIONE: amministrativa (data di comodo, subito dopo la semina),
  nessuna osservazione reale di questo passo intermedio.
- LUCE: osservazione reale riportata da Matteo il 29/9/2026 ("passa da
  ieri in luce", cioe' 28/9).

Idempotente: controlla prima se esiste gia' una semina su questo lotto
con questa data di avvio, e salta se trovata. Legge la versione del
lotto seme dal vivo un istante prima del commissioning (mai un dato
invecchiato).

Include anche una verifica READ-ONLY delle semine Cilantro piu' recenti,
per confermare se il nuovo lotto Cilantro (4 SET, seminato il 28/9,
inserito ieri tramite il diario) risulta davvero scritto nel database.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python scripts/commissioning/2026-09-29_completa_afila_nuovo_lotto.py
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
FORNITORE = "Golinucci Organic"
REFERENZA = "Pea Green Affila"
PHYSICAL_STARTED_AT = "2026-09-20T09:00:00+01:00"
GERMINAZIONE_AT = "2026-09-20T09:00:05+01:00"
LUCE_AT = "2026-09-28T09:00:00+01:00"
SET_QUANTITY = 4


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
        """SELECT pv.public_id, pv.stato_approvazione, pv.valida_al, pv.grammi_seme_per_set
           FROM tpo.protocollo_versioni pv
           JOIN tpo.protocolli p ON p.id = pv.protocollo_id
           JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id
           JOIN tpo.cultivar c ON c.id = cu.cultivar_id
           JOIN tpo.varieta v ON v.id = c.varieta_id
           WHERE v.codice_tracciabilita = 'AFI' AND pv.valida_al IS NULL
           ORDER BY pv.numero_versione DESC LIMIT 1"""
    )
    pv_row = cur.fetchone()
    if pv_row is None:
        raise SystemExit("Nessun protocollo Afila corrente (valida_al IS NULL) trovato -- FERMO.")
    pv_public_id, pv_stato, pv_valida_al, grammi_per_set = pv_row
    print(f"Protocollo Afila corrente: {pv_public_id} stato={pv_stato} grammi_per_set={grammi_per_set}")

    cur.execute(
        """SELECT si.id FROM tpo.semente_impieghi si
           JOIN tpo.sementi s ON s.id = si.semente_id
           JOIN tpo.cultivar_usi cu ON cu.id = si.cultivar_uso_id
           JOIN tpo.protocolli p ON p.cultivar_uso_id = cu.id
           JOIN tpo.protocollo_versioni pv ON pv.protocollo_id = p.id
           WHERE s.fornitore = %s AND s.referenza_commerciale = %s AND pv.public_id = %s""",
        (FORNITORE, REFERENZA, pv_public_id),
    )
    impiego_exists = cur.fetchone() is not None
    print(f"Semente-impiego {FORNITORE}/{REFERENZA} -> {pv_public_id}: "
          f"{'GIA ESISTENTE' if impiego_exists else 'DA CREARE'}")

    cur.execute(
        """SELECT s.public_id, s.stato FROM tpo.semine s
           JOIN tpo.lotti_seme l ON l.id = s.lotto_seme_id
           WHERE l.public_id = %s AND s.data_avvio = %s""",
        (LSE, "2026-09-20T09:00:00+01:00"),
    )
    already = cur.fetchone()
conn.close()

if already:
    print(f"Semina gia' registrata: {already} -- non commissiono di nuovo.")
    sem_public_id = already[0]
else:
    grammi = int(grammi_per_set) * SET_QUANTITY
    print(f"Da commissionare: {SET_QUANTITY} SET x {grammi_per_set}g = {grammi}g")
    if not impiego_exists:
        run_cli([
            RUN, "semente-impiego", "commission",
            "--fornitore", FORNITORE,
            "--referenza-commerciale", REFERENZA,
            "--protocol-version", pv_public_id,
            "--raccomandazione", "RACCOMANDATA",
            "--actor", "matteo",
            "--reason", "collegamento semente-protocollo per commissioning semina reale afila (secondo lotto)",
            "--correlation-id", "SEMENTE-IMPIEGO-2026-09-29-AFILA",
            "--idempotency-key", "semente-impiego-golinucci-pea-green-affila-" + pv_public_id.lower(),
            "--confirm",
        ], "semente-impiego Afila")

    conn2 = psycopg.connect(
        host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
        user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
        connect_timeout=parameters["connect_timeout"],
    )
    with conn2.cursor() as cur:
        cur.execute("SELECT version FROM tpo.lotti_seme WHERE public_id=%s", (LSE,))
        seed_lot_version = cur.fetchone()[0]
    conn2.close()

    out = run_cli([
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
        "--reason", "semina reale afila (secondo lotto) del 20/9 ore 9:00, registrata in ritardo "
                    "nel sistema (scoperta mancante il 29/9)",
        "--correlation-id", "SEMINA-2026-09-20-AFILA-2",
        "--idempotency-key", "semina-lse-000014-2026-09-20",
        "--confirm",
    ], "semina Afila (nuovo lotto)")
    sem_public_id = None
    for line in out.splitlines():
        if line.startswith("PUBLIC_ID:"):
            sem_public_id = line.split(":", 1)[1].strip()
    if not sem_public_id:
        raise SystemExit("Commissioning riuscito ma non ho trovato PUBLIC_ID nell'output -- controlla a mano.")
    print(f"Semina commissionata: {sem_public_id}")

# Transizioni verso LUCE
conn3 = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
with conn3.cursor() as cur:
    cur.execute("SELECT stato, version FROM tpo.semine WHERE public_id=%s", (sem_public_id,))
    stato, version = cur.fetchone()
conn3.close()
print(f"{sem_public_id}: stato attuale={stato} version={version}")

ORDER = ["AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA", "CHIUSA"]
STEPS = [("GERMINAZIONE", GERMINAZIONE_AT), ("LUCE", LUCE_AT)]
idx = ORDER.index(stato)
current_version = version
for target_state, effective_at in STEPS:
    if ORDER.index(target_state) <= idx:
        print(f"{sem_public_id}: gia' oltre {target_state}, salto.")
        continue
    reason = (
        f"Transizione a LUCE per Afila ({sem_public_id}), riportata da Matteo il 29/9/2026 "
        f"(fine germinazione, passaggio a luce avvenuto ieri, 28/9)."
        if target_state == "LUCE" else
        f"Transizione amministrativa GERMINAZIONE (data di comodo, non osservazione reale) "
        f"per {sem_public_id}, passo necessario prima della transizione a LUCE richiesta da Matteo."
    )
    cmd = [
        RUN, "semina", "transition",
        "--semina", sem_public_id,
        "--expected-semina-version", str(current_version),
        "--target-state", target_state,
        "--effective-at", effective_at,
        "--provenance", '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED"}',
        "--actor", "matteo",
        "--reason", reason,
        "--correlation-id", f"SEMINA-LIFECYCLE-2026-09-29-AFILA-{target_state}",
        "--idempotency-key", f"lifecycle-{sem_public_id.lower()}-{target_state.lower()}-2026-09-29",
        "--confirm",
    ]
    run_cli(cmd, f"{sem_public_id} -> {target_state}")
    current_version += 1

print("=== FATTO ===")

# Verifica read-only: Cilantro seminato di recente (nuovo lotto 4 SET, 28/9)
print()
print("=== VERIFICA: semine Cilantro piu' recenti (per controllare il nuovo lotto 4 SET) ===")
conn4 = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
with conn4.cursor() as cur:
    cur.execute(
        """SELECT s.public_id, s.codice_tracciabilita, s.stato, s.data_avvio, s.quantita_seme, s.unita_misura
           FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id
           WHERE v.codice_tracciabilita = 'CIL' ORDER BY s.data_avvio DESC LIMIT 5"""
    )
    for row in cur.fetchall():
        print(row)
conn4.close()
