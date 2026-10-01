"""Commissiona 4 delle 7 semine reali di oggi (1/10/2026), dettate da
Matteo prima di uscire ("2 set cilantro, 2 set mizuna, 3 set rabano, 1
rucola, 2 basilco 1 amaranto e 1 pak choy", "tutti stamattina", "cilantro
idratato ieri sera e piantato oggi") e confermate al suo ritorno ("ok,
iniziamo dal punto primo, cliente lo stabiliremo dopo").

Qui SOLO le 4 varieta' con catena protocollo+seme+lotto gia' completa a
sistema (vedi 2026-10-01_check_protocolli_semine_oggi.py):
  - Cilantro 2 SET (14g/set ufficiale -> 28g)
  - Mizuna   2 SET (10g/set ufficiale -> 20g)
  - Rabano   3 SET (14g/set ufficiale -> 42g), lotto Golinucci esplicitamente
             scelto da Matteo ("rabano golinucci, i semi hy farm sono
             pochissimi e li manteniamo a modo stock storico")
  - Amaranto 1 SET (10g/set ufficiale -> 10g)

NON incluse qui (bloccate, gestite separatamente):
  - Rucola e Pak Choi: richiedono prima
    2026-10-01_commission_protocolli_rucola_pakchoy.py (protocollo v1),
    e inoltre nessuna SEMENTE/SEMENTE_IMPIEGO/LOTTO_SEME esiste ancora
    per loro -- dato mai fornito, da chiedere a Matteo.
  - Basilico: protocollo PV-000006 esiste ma NESSUN SEMENTE_IMPIEGO/LOTTO
    risulta collegato al suo cultivar_uso -- stesso gap, dato da chiedere.

origin=RIPRISTINO_STOCK per tutte (nessun cliente/ordine assegnato,
fase transitoria esplicitamente dichiarata da Matteo: "cliente lo
stabiliremo dopo").

Orario fisico di avvio: placeholder 08:00 di oggi per tutte (Matteo ha
detto solo "tutti stamattina", nessun orario esatto fornito) -- se vuoi
un orario diverso, cambia PHYSICAL_HOUR prima di eseguire. Non influisce
sul codice di tracciabilita' (basato su giorno/mese) ne' sulla validita'
del protocollo (stessa data).

Rucola e Rabano: per Rabano si usa il lotto Golinucci richiesto
esplicitamente; per le altre si prende dinamicamente il LOTTO_SEME con
raccomandazione migliore e scorta sufficiente, mai hardcoded.

Idempotente: se una semina della stessa varieta' con data_avvio = oggi
esiste gia', salta quella varieta'.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python3 scripts/commissioning/2026-10-01_commission_semine_oggi.py
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
    {"denominazione": "Cilantro", "sigla": "CIL", "set": 2, "grams_per_set": 14,
     "fornitore_filter": None, "minute": 0},
    {"denominazione": "Mizuna", "sigla": "MIZ", "set": 2, "grams_per_set": 10,
     "fornitore_filter": None, "minute": 5},
    {"denominazione": "Rábano", "sigla": "RAB", "set": 3, "grams_per_set": 14,
     "fornitore_filter": "Golinucci", "minute": 10},
    {"denominazione": "Amaranto", "sigla": "AMA", "set": 1, "grams_per_set": 10,
     "fornitore_filter": None, "minute": 15},
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
        raise SystemExit(f"{nome}: trovate {len(rows)} protocollo_versioni APPROVATA correnti, attesa 1. Fermo qui.")
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
                "SELECT public_id FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id "
                "WHERE v.codice_tracciabilita = %s AND s.data_avvio::date = %s",
                (sigla, TODAY.date()),
            )
            existing = cur.fetchall()
            if existing:
                print(f"{nome}: semina di oggi gia' commissionata ({existing[0][0]}). Salto.")
                continue

            pv_public_id = resolve_protocol_version(cur, nome)
            lse_public_id, lse_version = resolve_seed_lot(
                cur, nome, var["set"] * var["grams_per_set"], var["fornitore_filter"],
            )
            total_grams = var["set"] * var["grams_per_set"]
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
                "--actual-seed-grams", str(total_grams),
                "--physical-started-at", started_at.isoformat(),
                "--origin", "RIPRISTINO_STOCK",
                "--provenance", '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}',
                "--actor", "matteo",
                "--reason", (
                    f"Semina reale {nome} di oggi 1/10/2026 ({var['set']} SET, {total_grams}g), "
                    f"dettata da Matteo prima di uscire; cliente/ordine da assegnare in seguito "
                    f"(fase transitoria, cfr. appunti-in-sospeso-2026-10-01.md)."
                ),
                "--correlation-id", corr,
                "--idempotency-key", idem,
                "--confirm",
            ], f"commissiona semina {nome} ({var['set']} SET, {total_grams}g, {lse_public_id})")

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
