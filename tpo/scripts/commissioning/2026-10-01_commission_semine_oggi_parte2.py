"""Commissiona le 3 semine reali di oggi (1/10/2026) rimaste bloccate nello
script precedente (2026-10-01_commission_semine_oggi.py): Basilico, Rucola,
Pak Choi. Richiede, nell'ordine:
  1. 2026-10-01_commission_protocolli_rucola_pakchoy.py (crea i protocolli
     v1 per Rucola/Pak Choi -- Basilico li ha gia')
  2. 2026-10-01_commission_semente_impieghi_intersemillas.py (collega le
     sementi Intersemillas, gia' commissionate da tempo, ai 3 protocolli)

Quantita' dettate da Matteo ("2 set cilantro, 2 set mizuna, 3 set rabano,
1 rucola, 2 basilco 1 amaranto e 1 pak choy"):
  - Basilico 2 SET, 8g/set ufficiale -> 16g
  - Rucola   1 SET, grammi REALI usati oggi 7g (test -- protocollo resta
    8g/set ufficiale, non cambiato; "il test non va registrato ... se si
    prende la decisione sara' prontamente comunicata" => qui si registra
    solo il fatto fisico reale, 7g, non il protocollo)
  - Pak Choi 1 SET, 10g/set ufficiale -> 10g (nessun test sui grammi,
    solo su germinazione/luce)

Seme: Intersemillas per tutte e tre (confermato da Matteo il 1/10/2026).

origin=RIPRISTINO_STOCK, nessun cliente/ordine assegnato (fase
transitoria). Stesso placeholder di orario fisico (08:00) dello script
precedente -- modificabile in PHYSICAL_HOUR se vuoi un orario preciso.

Idempotente: se una semina della stessa varieta' con data_avvio = oggi
esiste gia', salta quella varieta'.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python3 scripts/commissioning/2026-10-01_commission_semine_oggi_parte2.py
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

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
TZ = timezone(timedelta(hours=1))
TODAY = datetime(2026, 10, 1)
PHYSICAL_HOUR = 8  # placeholder: Matteo ha detto solo "tutti stamattina"

SEMINE = [
    {"denominazione": "Basilico", "sigla": "ALB", "set": 2, "actual_grams": 16, "minute": 20},
    {"denominazione": "Rucola", "sigla": "RUC", "set": 1, "actual_grams": 7, "minute": 25},
    {"denominazione": "Pak Choi", "sigla": "PAK", "set": 1, "actual_grams": 10, "minute": 30},
]
FORNITORE_FILTER = "Intersemillas"


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


def resolve_protocol_version(cur, nome):
    cur.execute(
        """SELECT pv.public_id
           FROM tpo.protocollo_versioni pv
           JOIN tpo.protocolli p ON p.id = pv.protocollo_id
           JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id
           JOIN tpo.cultivar c ON c.id = cu.cultivar_id
           JOIN tpo.varieta v ON v.id = c.varieta_id
           JOIN tpo.usi_produttivi up ON up.id = cu.uso_produttivo_id AND up.codice = 'MICROGREEN'
           WHERE v.denominazione = %s AND pv.stato_approvazione = 'APPROVATA'
             AND pv.valida_al IS NULL""",
        (nome,),
    )
    rows = cur.fetchall()
    if len(rows) != 1:
        raise SystemExit(
            f"{nome}: trovate {len(rows)} protocollo_versioni APPROVATA correnti, attesa 1 "
            f"(hai eseguito gli script precedenti nell'ordine giusto?). Fermo qui."
        )
    return rows[0][0]


def resolve_seed_lot(cur, nome, needed_grams, fornitore_filter):
    cur.execute(
        """SELECT s.id, s.fornitore, si.raccomandazione, si.rating
           FROM tpo.semente_impieghi si
           JOIN tpo.sementi s ON s.id = si.semente_id
           JOIN tpo.cultivar_usi cu ON cu.id = si.cultivar_uso_id
           JOIN tpo.cultivar c ON c.id = cu.cultivar_id
           JOIN tpo.varieta v ON v.id = c.varieta_id
           WHERE v.denominazione = %s AND si.raccomandazione IN ('RACCOMANDATA', 'UTILIZZABILE')
           ORDER BY si.raccomandazione, si.rating DESC NULLS LAST""",
        (nome,),
    )
    impieghi = cur.fetchall()
    if fornitore_filter:
        impieghi = [row for row in impieghi if fornitore_filter.lower() in row[1].lower()]
    if not impieghi:
        raise SystemExit(f"{nome}: nessun semente_impiego eleggibile trovato (fornitore_filter={fornitore_filter!r}). Fermo qui.")
    for (semente_id, fornitore, racc, rating) in impieghi:
        cur.execute(
            """SELECT public_id, version, quantita_residua
               FROM tpo.lotti_seme
               WHERE semente_id = %s AND anomalia IS NULL
                 AND (data_scadenza IS NULL OR data_scadenza >= %s)
                 AND quantita_residua >= %s
               ORDER BY data_ricezione DESC LIMIT 1""",
            (semente_id, TODAY.date(), needed_grams),
        )
        row = cur.fetchone()
        if row:
            lse_pid, version, residuo = row
            print(f"{nome}: lotto scelto {lse_pid} (fornitore {fornitore}, residuo {residuo}g, raccomandazione {racc})")
            return lse_pid, version
    raise SystemExit(f"{nome}: nessun lotto con scorta sufficiente ({needed_grams}g) trovato. Fermo qui.")


conn = db()
try:
    with conn.cursor() as cur:
        for var in SEMINE:
            nome = var["denominazione"]
            sigla = var["sigla"]
            print(f"=== {nome} ({sigla}) ===")
            cur.execute(
                "SELECT s.public_id FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id "
                "WHERE v.codice_tracciabilita = %s AND s.data_avvio::date = %s",
                (sigla, TODAY.date()),
            )
            existing = cur.fetchall()
            if existing:
                print(f"{nome}: semina di oggi gia' commissionata ({existing[0][0]}). Salto.")
                continue

            pv_public_id = resolve_protocol_version(cur, nome)
            lse_public_id, lse_version = resolve_seed_lot(
                cur, nome, var["actual_grams"], FORNITORE_FILTER,
            )
            started_at = TODAY.replace(
                hour=PHYSICAL_HOUR, minute=var["minute"], second=0, tzinfo=TZ,
            )
            idem = f"semina-{sigla.lower()}-2026-10-01"
            corr = f"SEMINA-2026-10-01-{sigla}"

            out = run_cmd([
                RUN, "semina", "commission",
                "--seed-lot", lse_public_id,
                "--expected-seed-lot-version", str(lse_version),
                "--protocol-version", pv_public_id,
                "--actual-seed-grams", str(var["actual_grams"]),
                "--physical-started-at", started_at.isoformat(),
                "--origin", "RIPRISTINO_STOCK",
                "--provenance", '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}',
                "--actor", "matteo",
                "--reason", (
                    f"Semina reale {nome} di oggi 1/10/2026 ({var['set']} SET, {var['actual_grams']}g "
                    f"effettivi), dettata da Matteo prima di uscire; cliente/ordine da assegnare in "
                    f"seguito (fase transitoria, cfr. appunti-in-sospeso-2026-10-01.md)."
                ),
                "--correlation-id", corr,
                "--idempotency-key", idem,
                "--confirm",
            ], f"commissiona semina {nome} ({var['set']} SET, {var['actual_grams']}g, {lse_public_id})")

            sem_pid = trace = None
            for line in out.splitlines():
                if line.startswith("PUBLIC_ID:"):
                    sem_pid = line.split(":", 1)[1].strip()
                if line.startswith("TRACEABILITY_CODE:"):
                    trace = line.split(":", 1)[1].strip()
            print(f"{nome}: semina {sem_pid}, codice tracciabilita {trace}")
            print()
finally:
    conn.close()

print("=== FATTO ===")
