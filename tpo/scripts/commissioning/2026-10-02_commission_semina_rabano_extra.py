"""Commissiona la semina REALE di Rabano fatta da Matteo oggi (2/10/2026,
ore 11:00, 14g = 1 SET al grammaggio ufficiale 14g/set), per coprire il
fabbisogno della settimana 5-11/10 individuato dal report
`2026-10-02_fabbisogno_set_prossima_settimana.py`.

Formula occasionale, dettata da Matteo in chat: "14 g piantoto alle
11.00". Niente di nuovo da costruire -- stesso protocollo Rabano gia'
esistente, stesso lotto Golinucci usato ieri (esplicitamente preferito
da Matteo: "rabano golinucci, i semi hy farm sono pochissimi e li
manteniamo a modo stock storico"), stessa identica procedura di
commissioning SEMINA usata tutta la giornata del 1/10.

NON si riusa il codice di tracciabilita' di ieri (RAB-0110-A): questa e'
una semina fisica diversa, avvenuta oggi, e riceve correttamente il suo
proprio codice (basato sulla data reale di oggi) dal comando governato
stesso -- cosi' la tracciabilita' resta onesta rispetto a quando e'
stata realmente piantata.

origin=RIPRISTINO_STOCK (nessun cliente/ordine specifico assegnato,
copertura di fabbisogno generale individuato dal report settimanale).

Idempotente: se una semina di Rabano con data_avvio = oggi esiste gia',
salta.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python3 scripts/commissioning/2026-10-02_commission_semina_rabano_extra.py
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
TODAY = datetime(2026, 10, 2)

NOME = "Rábano"
SIGLA = "RAB"
TOTAL_GRAMS = 14
FORNITORE_FILTER = "Golinucci"
PHYSICAL_HOUR = 11
PHYSICAL_MINUTE = 0


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
        print(f"=== {NOME} ({SIGLA}) -- extra 2/10/2026 ===")
        cur.execute(
            "SELECT s.public_id FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id "
            "WHERE v.codice_tracciabilita = %s AND s.data_avvio::date = %s",
            (SIGLA, TODAY.date()),
        )
        existing = cur.fetchall()
        if existing:
            print(f"{NOME}: semina di oggi gia' commissionata ({existing[0][0]}). Salto.")
        else:
            pv_public_id = resolve_protocol_version(cur, NOME)
            lse_public_id, lse_version = resolve_seed_lot(
                cur, NOME, TOTAL_GRAMS, FORNITORE_FILTER,
            )
            started_at = TODAY.replace(
                hour=PHYSICAL_HOUR, minute=PHYSICAL_MINUTE, second=0, tzinfo=TZ,
            )
            idem = f"semina-{SIGLA.lower()}-2026-10-02-extra"
            corr = f"SEMINA-2026-10-02-{SIGLA}-EXTRA"

            out = run_cmd([
                RUN, "semina", "commission",
                "--seed-lot", lse_public_id,
                "--expected-seed-lot-version", str(lse_version),
                "--protocol-version", pv_public_id,
                "--actual-seed-grams", str(TOTAL_GRAMS),
                "--physical-started-at", started_at.isoformat(),
                "--origin", "RIPRISTINO_STOCK",
                "--provenance", '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}',
                "--actor", "matteo",
                "--reason", (
                    f"Semina reale extra {NOME} del 2/10/2026 ({TOTAL_GRAMS}g, 1 SET), "
                    f"dettata da Matteo ('14 g piantoto alle 11.00') per coprire il "
                    f"fabbisogno Rabano della settimana 5-11/10 individuato dal report "
                    f"settimanale; cliente/ordine da assegnare in seguito."
                ),
                "--correlation-id", corr,
                "--idempotency-key", idem,
                "--confirm",
            ], f"commissiona semina extra {NOME} (1 SET, {TOTAL_GRAMS}g, {lse_public_id})")

            sem_pid = trace = None
            for line in out.splitlines():
                if line.startswith("PUBLIC_ID:"):
                    sem_pid = line.split(":", 1)[1].strip()
                if line.startswith("TRACEABILITY_CODE:"):
                    trace = line.split(":", 1)[1].strip()
            print(f"{NOME}: semina {sem_pid}, codice tracciabilita {trace}")
finally:
    conn.close()

print("\n=== FATTO ===")
