"""Collega (SEMENTE_IMPIEGO) le sementi Intersemillas, gia' commissionate
da tempo (2026-09-06/07, vedi handoff/catalogo-varieta-semi.md) ma mai
collegate a nessun protocollo, per Basilico/Rucola/Pak Choi -- lo sblocco
per queste 3 semine di oggi che credevo richiedesse nuovi dati di
approvvigionamento. Matteo ha confermato che i dati esistono gia'
("attualmente per tutte e tre stiamo utilizzando intersemillas") -- qui
NON si inventa/richiede nulla di nuovo, si collega solo quanto gia'
a sistema:

  Basilico (Albahaca) -> SEMENTE id 3 / LSE-000003 (Intersemillas, MG-00446)
  Rucola   (Rucula)   -> SEMENTE id 4 / LSE-000004 (Intersemillas, MG-00479)
  Pak Choi             -> SEMENTE id 6 / LSE-000006 (Intersemillas, MG-00411)

(Basilico e Rucola hanno anche un secondo fornitore Golinucci in stock --
Basil Green/LSE-000008 e Rocket Cultivated/LSE-000007 -- ma Matteo ha
detto esplicitamente che oggi si usa Intersemillas per tutte e tre, quindi
qui si collega solo quello, non il Golinucci.)

fornitore/referenza_commerciale NON sono hardcoded da un ricordo: vengono
letti dalla riga reale in tpo.sementi (fornitore ILIKE 'Intersemillas',
referenza_commerciale ILIKE la parola chiave), cosi' il match
case-insensitive/trim del writer (lower(btrim(...))) e' garantito esatto.

Basilico: puo' essere eseguito subito (protocollo PV-000006 esiste da
tempo). Rucola/Pak Choi: richiedono che
2026-10-01_commission_protocolli_rucola_pakchoy.py sia stato eseguito
PRIMA (serve il loro protocollo/cultivar_uso, che ancora non esiste).

Idempotente: se il link semente_impieghi esiste gia' per quella
combinazione (semente, cultivar_uso), salta.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python3 scripts/commissioning/2026-10-01_commission_semente_impieghi_intersemillas.py
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

LINKS = [
    {"denominazione": "Basilico", "keyword": "Albahaca", "correlation_id": "SEMENTE-IMPIEGO-BASILICO-2026-10-01"},
    {"denominazione": "Rucola", "keyword": "Rucula", "correlation_id": "SEMENTE-IMPIEGO-RUCOLA-2026-10-01"},
    {"denominazione": "Pak Choi", "keyword": "Pak Choi", "correlation_id": "SEMENTE-IMPIEGO-PAKCHOY-2026-10-01"},
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


conn = db()
try:
    with conn.cursor() as cur:
        for link in LINKS:
            nome = link["denominazione"]
            print(f"=== {nome} ===")

            cur.execute(
                """SELECT id, fornitore, referenza_commerciale FROM tpo.sementi
                   WHERE fornitore ILIKE 'Intersemillas' AND referenza_commerciale ILIKE %s""",
                (f"%{link['keyword']}%",),
            )
            rows = cur.fetchall()
            if len(rows) != 1:
                raise SystemExit(
                    f"{nome}: trovate {len(rows)} righe sementi per Intersemillas/{link['keyword']}, attesa 1. Fermo qui."
                )
            semente_id, fornitore, referenza = rows[0]
            print(f"{nome}: semente trovata id={semente_id} '{fornitore}' / '{referenza}'")

            cur.execute(
                """SELECT pv.public_id, p.cultivar_uso_id
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
            prow = cur.fetchall()
            if len(prow) != 1:
                raise SystemExit(
                    f"{nome}: trovate {len(prow)} protocollo_versioni APPROVATA correnti, attesa 1 "
                    f"(se Rucola/Pak Choi: hai eseguito prima 2026-10-01_commission_protocolli_rucola_pakchoy.py?). Fermo qui."
                )
            pv_public_id, cultivar_uso_id = prow[0]

            cur.execute(
                "SELECT id FROM tpo.semente_impieghi WHERE semente_id = %s AND cultivar_uso_id = %s",
                (semente_id, cultivar_uso_id),
            )
            if cur.fetchone():
                print(f"{nome}: semente_impiego gia' esistente per questa combinazione. Salto.")
                continue

            run_cmd([
                RUN, "semente-impiego", "commission",
                "--fornitore", fornitore,
                "--referenza-commerciale", referenza,
                "--protocol-version", pv_public_id,
                "--raccomandazione", "RACCOMANDATA",
                "--motivazione", (
                    f"Seme attualmente in uso per {nome} (confermato da Matteo il 1/10/2026: "
                    f"\"attualmente per tutte e tre stiamo utilizzando intersemillas\")."
                ),
                "--actor", "matteo",
                "--reason", (
                    f"Collegare la semente Intersemillas (gia' commissionata dal 2026-09-06/07, "
                    f"mai collegata) al protocollo {nome}, per sbloccare il commissioning SEMINA "
                    f"reale di oggi 1/10/2026."
                ),
                "--correlation-id", link["correlation_id"],
                "--idempotency-key", f"semente-impiego-{nome.lower().replace(' ', '')}-intersemillas-2026-10-01",
                "--confirm",
            ], f"collega semente Intersemillas/{referenza} a {nome} ({pv_public_id})")
            print()
finally:
    conn.close()

print("=== FATTO ===")
