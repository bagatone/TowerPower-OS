"""Crea i protocolli di coltivazione v1 per Rucola e Pak Choi (microgreens),
mai commissionati finora (VARIETA onboardata ma nessuna riga
cultivar/cultivar_uso/protocollo/protocollo_versione esisteva -- vedi
2026-10-01_check_protocolli_semine_oggi.py).

A differenza dello script analogo per Amaranto (2026-09-15, quando il
comando CLI non esisteva ancora e si chiamava il service applicativo
direttamente), qui usiamo il comando governato reale 'tpo protocollo
commission' (src/tpo_core/cli/protocollo.py + main.py), appena collegato
e verificato con 32/32 test da Matteo il 1/10/2026 -- e' esattamente il
comando richiesto ("costruiamo il comando per rucola e pak").

Dati agronomici forniti da Matteo in chat il 1/10/2026:
  Rucola:   idratazione 0h, germinazione 5gg, luce 8gg (SPERIMENTALE,
            non ufficiale -- test in corso, Matteo ha detto esplicitamente
            "il test non va registrato ... assolutamente non cambiare 8g"),
            8g semi/SET (valore UFFICIALE -- oggi si e' seminato con 7g
            solo come test, ma il protocollo resta a 8g).
  Pak Choi: idratazione 0h, germinazione 6gg, luce 8gg (sperimentale,
            stessa cautela), 10g semi/SET (ufficiale, confermato anche
            in precedenza "pak choy 10").

Conferma finale di Matteo per procedere ora nonostante crescita_luce_giorni
sia ancora sperimentale: "no, crealo e poi aggiorneremo a ver2 senza
alcun problema, giusto?" (1/10/2026).

Tutti gli altri parametri (orario semina/raccolta, resa attesa,
granularita' produttiva, harvest lead, buffer, cultivar_name = variety_name,
productive_use_code/name, actor) sono presi identici agli 8 protocolli
STANDARD reali gia' esistenti, stesso schema usato per Amaranto
(2026-09-15_crea_protocollo_amaranto.py) -- farm standard operativo, non
agronomia specifica di varieta'.

valid_from = 2026-10-01 (oggi, prima semina reale di entrambe).

Idempotente: se una riga cultivar per Rucola/Pak Choi con uso MICROGREEN
esiste gia' con un protocollo APPROVATA, salta quella varieta'.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python3 scripts/commissioning/2026-10-01_commission_protocolli_rucola_pakchoy.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")

VALID_FROM = "2026-10-01"
UNIVERSAL_DEFAULTS = dict(
    planned_sowing_time="06:00",
    target_harvest_time="06:00",
    expected_yield="1",
    production_granularity="0.5",
    harvest_min_lead_days="1",
    harvest_max_lead_days="1",
    temporal_buffer_minutes="0",
)

VARIETIES = [
    {
        "denominazione": "Rucola",
        "hydration_hours": "0",
        "germination_days": "5",
        "light_growth_days": "8",
        "seed_grams_per_set": "8",
        "correlation_id": "PROTOCOLLO-RUCOLA-2026-10-01",
    },
    {
        "denominazione": "Pak Choi",
        "hydration_hours": "0",
        "germination_days": "6",
        "light_growth_days": "8",
        "seed_grams_per_set": "10",
        "correlation_id": "PROTOCOLLO-PAKCHOY-2026-10-01",
    },
]


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


def next_pv_public_id(cur, taken: set[str]) -> str:
    cur.execute("SELECT public_id FROM tpo.protocollo_versioni")
    numbers = [int(re.fullmatch(r"PV-([0-9]{6,})", row[0]).group(1)) for row in cur.fetchall()]
    for already in taken:
        numbers.append(int(re.fullmatch(r"PV-([0-9]{6,})", already).group(1)))
    nxt = max(numbers, default=0) + 1
    pid = f"PV-{nxt:06d}"
    taken.add(pid)
    return pid


conn = db()
try:
    with conn.cursor() as cur:
        assigned_pv: set[str] = set()
        for var in VARIETIES:
            nome = var["denominazione"]
            print(f"=== {nome} ===")
            cur.execute(
                """SELECT v.public_id, cu.id, p.id, pv.public_id, pv.stato_approvazione
                   FROM tpo.varieta v
                   JOIN tpo.cultivar c ON c.varieta_id = v.id
                   JOIN tpo.cultivar_usi cu ON cu.cultivar_id = c.id
                   JOIN tpo.usi_produttivi up ON up.id = cu.uso_produttivo_id AND up.codice = 'MICROGREEN'
                   LEFT JOIN tpo.protocolli p ON p.cultivar_uso_id = cu.id
                   LEFT JOIN tpo.protocollo_versioni pv ON pv.protocollo_id = p.id
                   WHERE v.denominazione = %s""",
                (nome,),
            )
            existing = cur.fetchall()
            if existing and any(row[4] == "APPROVATA" for row in existing):
                pv_pid = next(row[3] for row in existing if row[4] == "APPROVATA")
                print(f"{nome}: protocollo MICROGREEN gia' esistente e APPROVATA ({pv_pid}). Salto.")
                continue

            cur.execute("SELECT public_id FROM tpo.varieta WHERE denominazione = %s", (nome,))
            row = cur.fetchone()
            if not row:
                raise SystemExit(f"VARIETA '{nome}' non trovata a sistema. Fermo qui, nessuna azione.")
            variety_public_id = row[0]
            pv_public_id = next_pv_public_id(cur, assigned_pv)
            print(f"{nome}: variety_id={variety_public_id}, nuovo protocol_version_id={pv_public_id}")

            content = (
                f"hydration_hours={var['hydration_hours']}; "
                f"germination_days={var['germination_days']}; "
                f"light_growth_days={var['light_growth_days']} (SPERIMENTALE, non ufficiale - "
                f"test in corso, v2 prevista quando confermato); "
                f"seed_grams_per_set={var['seed_grams_per_set']}"
            )
            motivation = (
                f"Creazione protocollo v1 {nome} (microgreens), dati forniti da Matteo in chat "
                f"il 1/10/2026. crescita_luce_giorni={var['light_growth_days']} e' ancora in fase "
                f"sperimentale (test in corso, non ufficiale): Matteo ha autorizzato esplicitamente "
                f"la creazione della v1 ora con questo valore, con l'intesa di aggiornare a v2 non "
                f"appena il test sara' validato ('no, crealo e poi aggiorneremo a ver2 senza alcun "
                f"problema'). seed_grams_per_set resta al valore ufficiale, non al valore di test."
            )
            reason = (
                f"Sbloccare il commissioning SEMINA reale di {nome}, pianificato/seminato oggi "
                f"1/10/2026, privo finora di qualunque protocollo di coltivazione a sistema."
            )

            run_cmd([
                RUN, "protocollo", "commission",
                "--variety-id", variety_public_id,
                "--variety-name", nome,
                "--cultivar-name", nome,
                "--productive-use-code", "MICROGREEN",
                "--productive-use-name", "Microgreens",
                "--protocol-name", f"Tower Power standard {nome}",
                "--protocol-version-id", pv_public_id,
                "--version", "1",
                "--valid-from", VALID_FROM,
                "--hydration-hours", var["hydration_hours"],
                "--planned-sowing-time", UNIVERSAL_DEFAULTS["planned_sowing_time"],
                "--target-harvest-time", UNIVERSAL_DEFAULTS["target_harvest_time"],
                "--germination-days", var["germination_days"],
                "--light-growth-days", var["light_growth_days"],
                "--seed-grams-per-set", var["seed_grams_per_set"],
                "--expected-yield", UNIVERSAL_DEFAULTS["expected_yield"],
                "--production-granularity", UNIVERSAL_DEFAULTS["production_granularity"],
                "--harvest-min-lead-days", UNIVERSAL_DEFAULTS["harvest_min_lead_days"],
                "--harvest-max-lead-days", UNIVERSAL_DEFAULTS["harvest_max_lead_days"],
                "--temporal-buffer-minutes", UNIVERSAL_DEFAULTS["temporal_buffer_minutes"],
                "--content", content,
                "--motivation", motivation,
                "--provenance", "OWNER_AUTHORIZED_REAL_GROWING_PROTOCOL_2026-10",
                "--actor", "tpo.owner",
                "--reason", reason,
                "--correlation-id", var["correlation_id"],
                "--confirm",
            ], f"commissiona protocollo {nome} v1 ({pv_public_id})")
            print()
finally:
    conn.close()

print("=== FATTO ===")
