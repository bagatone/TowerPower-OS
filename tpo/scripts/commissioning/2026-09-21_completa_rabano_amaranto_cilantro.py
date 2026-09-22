"""Completa (senza duplicare nulla) il commissioning delle tre semine
reali del 17/9/2026 ore 21:00 (Rabano 3 SET, Amaranto 1 SET, Cilantro 4
SET, origine RIPRISTINO_STOCK) gia' verificate nel Fatto 18 ma MAI
eseguite per davvero contro il Postgres di produzione (scoperto il
21/9/2026, Fatto 27: nessuna semina attiva trovata per Rabano).

Non inventa nulla di nuovo: fornitore/referenza/lotto seme/protocollo/
grammi sono gli stessi gia' verificati il 18/9
(2026-09-18_check_rabano_amaranto_cilantro.py). L'UNICA cosa che questo
script non riusa dal 18/9 e' la `--expected-seed-lot-version`: quella
viene riletta dal vivo un istante prima di ogni commissioning, perche'
tra il 18/9 e oggi il lotto seme puo' essere stato toccato da altri
movimenti (proprio il tipo di problema di dati "invecchiati" che questo
processo manuale genera).

Per ciascuna delle tre semine e per il collegamento semente->protocollo
del Rabano, controlla prima se esiste gia' (idempotenza reale, non solo
a livello di idempotency-key) e salta se trovato, cosi' e' sicuro
rilanciarlo piu' volte.
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

SEMINE = [
    dict(nome="Rabano", lse="LSE-000010", pv="PV-000002", grammi="42",
         corr="SEMINA-2026-09-17-RABANO", idem="semina-lse-000010-2026-09-17"),
    dict(nome="Amaranto", lse="LSE-000012", pv="PV-000007", grammi="10",
         corr="SEMINA-2026-09-17-AMARANTO", idem="semina-lse-000012-2026-09-17"),
    dict(nome="Cilantro", lse="LSE-000013", pv="PV-000003", grammi="56",
         corr="SEMINA-2026-09-17-CILANTRO", idem="semina-lse-000013-2026-09-17"),
]
PHYSICAL_STARTED_AT = "2026-09-17T21:00:00+01:00"


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
    # 1. Collegamento semente Golinucci/Radish Vulcano -> PV-000002 (Rabano)
    cur.execute(
        """SELECT si.id FROM tpo.semente_impieghi si
           JOIN tpo.sementi s ON s.id = si.semente_id
           JOIN tpo.cultivar_usi cu ON cu.id = si.cultivar_uso_id
           JOIN tpo.protocolli p ON p.cultivar_uso_id = cu.id
           JOIN tpo.protocollo_versioni pv ON pv.protocollo_id = p.id
           WHERE s.fornitore = 'Golinucci Organic'
             AND s.referenza_commerciale = 'Radish Vulcano'
             AND pv.public_id = 'PV-000002'"""
    )
    impiego_exists = cur.fetchone() is not None

    # 2. PV-000002 e' ancora la versione APPROVATA corrente? (mai revisionata nel frattempo)
    cur.execute(
        "SELECT stato_approvazione, valida_al FROM tpo.protocollo_versioni WHERE public_id='PV-000002'"
    )
    pv_row = cur.fetchone()

    # 3. Semine gia' esistenti per ciascun lotto seme target
    existing = {}
    for row in SEMINE:
        cur.execute(
            "SELECT s.public_id, s.stato FROM tpo.semine s JOIN tpo.lotti_seme l ON l.id=s.lotto_seme_id "
            "WHERE l.public_id=%s AND s.causa_origine='RIPRISTINO_STOCK'",
            (row["lse"],),
        )
        existing[row["lse"]] = cur.fetchone()

conn.close()

print(f"Semente-impiego Golinucci/Radish Vulcano -> PV-000002: "
      f"{'GIA ESISTENTE' if impiego_exists else 'DA CREARE'}")
print(f"PV-000002: stato_approvazione={pv_row[0]} valida_al={pv_row[1]}")
if pv_row[1] is not None:
    raise SystemExit(
        "PV-000002 risulta chiuso/revisionato (valida_al non nullo) -- NON PROSEGUO, "
        "serve rivedere manualmente quale versione usare ora."
    )
for row in SEMINE:
    found = existing[row["lse"]]
    print(f"{row['nome']} ({row['lse']}): {'GIA REGISTRATA -> ' + str(found) if found else 'DA COMMISSIONARE'}")

if not impiego_exists:
    run_cli([
        RUN, "semente-impiego", "commission",
        "--fornitore", "Golinucci Organic",
        "--referenza-commerciale", "Radish Vulcano",
        "--protocol-version", "PV-000002",
        "--raccomandazione", "RACCOMANDATA",
        "--actor", "giulia",
        "--reason", "collegamento semente-protocollo per commissioning semina reale rabano "
                    "(lotto Golinucci, non quello Hyfarm gia collegato)",
        "--correlation-id", "SEMENTE-IMPIEGO-2026-09-18-RABANO-GOLINUCCI",
        "--idempotency-key", "semente-impiego-golinucci-radish-vulcano-pv-000002",
        "--confirm",
    ], "semente-impiego Rabano")

conn2 = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
for row in SEMINE:
    if existing[row["lse"]]:
        print(f"{row['nome']}: salto, gia' registrata.")
        continue
    with conn2.cursor() as cur:
        cur.execute("SELECT version FROM tpo.lotti_seme WHERE public_id=%s", (row["lse"],))
        seed_lot_version = cur.fetchone()[0]
    run_cli([
        RUN, "semina", "commission",
        "--seed-lot", row["lse"],
        "--expected-seed-lot-version", str(seed_lot_version),
        "--protocol-version", row["pv"],
        "--actual-seed-grams", row["grammi"],
        "--physical-started-at", PHYSICAL_STARTED_AT,
        "--origin", "RIPRISTINO_STOCK",
        "--provenance", '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED",'
                        '"selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}',
        "--actor", "giulia",
        "--reason", f"semina reale {row['nome'].lower()} del 17/9 ore 21, registrata in ritardo nel "
                    f"sistema (scoperta mancante il 21/9, Fatto 27)",
        "--correlation-id", row["corr"],
        "--idempotency-key", row["idem"],
        "--confirm",
    ], f"semina {row['nome']}")
conn2.close()

print("=== FATTO ===")
