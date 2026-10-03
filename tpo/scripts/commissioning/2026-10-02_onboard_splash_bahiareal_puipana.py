"""Onboarding di 3 nuovi clienti via comandi governati reali (nessun
dato manuale sul DB: solo 'tpo onboarding customer' + 'tpo onboarding
supply-program'), secondo le richieste di Matteo in chat il 2/10/2026:

  - Splash: Cilantro 1 SET + Basilico 1 SET, settimanale martedi.
  - Hotel Secret Bahia Real: Afila 1 SET + Rabano 1 SET fissi,
    settimanale martedi (il 3 SET a rotazione varieta' NON e' automatizzato:
    Matteo lo decide a mano ogni lunedi finche' non hanno provato tutto il
    catalogo -- "bahia iniziamo con afila, rabano e l'ultimo set decidero
    lunedi in base a come sara lo stato della produzione").
  - Puipana: Afila 0.5 + Cilantro 0.5 + Mizuna 0.5 + Rabano 0.5 SET, ogni
    14 giorni. Prima consegna gia' avvenuta giovedi 1/10/2026
    ("consegna il giovedi (ieri)"); data_inizio=2026-10-01 cosi' il
    prossimo giro cade il 15/10/2026 (intervallo confermato a 14 giorni
    da Matteo: "puipana 14 giorni").

CLI-id e PF-id calcolati dinamicamente (MAX+1 sui public_id esistenti),
mai hardcoded. orario_generazione=05:00:00 e finestra_operativa_giorni=14
sono lo standard farm confermato su tutti i 9 programmi esistenti
(2026-10-02_dettaglio_programmi_fornitura.py).

Idempotente: se un CLIENTE con la stessa denominazione esiste gia', ne
riusa il public_id senza ricrearlo; se quel cliente ha gia' un
PROGRAMMA_FORNITURA, salta l'onboarding del programma.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python3 scripts/commissioning/2026-10-02_onboard_splash_bahiareal_puipana.py
"""
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
ACTOR = "matteo"
GENERATION_TIME = "05:00:00"
OPERATIONAL_WINDOW_DAYS = 14

CLIENTI = [
    {
        "denominazione": "Splash",
        "start_date": "2026-10-02",
        "lines": [
            "VAR-000003,1,SET,GIORNI_SETTIMANA,,2",  # Cilantro, martedi
            "VAR-000006,1,SET,GIORNI_SETTIMANA,,2",  # Basilico, martedi
        ],
        "reason": (
            "Nuovo cliente Splash, richiesto da Matteo 2/10/2026: 1 Cilantro "
            "+ 1 Basilico, settimanale martedi."
        ),
        "correlation_id": "ONBOARDING-SPLASH-2026-10-02",
    },
    {
        "denominazione": "Hotel Secret Bahia Real",
        "start_date": "2026-10-02",
        "lines": [
            "VAR-000001,1,SET,GIORNI_SETTIMANA,,2",  # Afila, martedi
            "VAR-000002,1,SET,GIORNI_SETTIMANA,,2",  # Rabano, martedi
        ],
        "reason": (
            "Nuovo cliente Hotel Secret Bahia Real, richiesto da Matteo "
            "2/10/2026: 2 dei 3 SET settimanali (Afila + Rabano, consegna "
            "martedi) sono fissi e automatizzati qui; il 3 SET e' a "
            "rotazione varieta' (fino a esaurimento catalogo) e NON e' "
            "automatizzato -- Matteo lo sceglie a mano ogni lunedi."
        ),
        "correlation_id": "ONBOARDING-BAHIAREAL-2026-10-02",
    },
    {
        "denominazione": "Puipana",
        "start_date": "2026-10-01",
        "lines": [
            "VAR-000001,0.5,SET,OGNI_X_GIORNI,14,",  # Afila
            "VAR-000003,0.5,SET,OGNI_X_GIORNI,14,",  # Cilantro
            "VAR-000004,0.5,SET,OGNI_X_GIORNI,14,",  # Mizuna
            "VAR-000002,0.5,SET,OGNI_X_GIORNI,14,",  # Rabano
        ],
        "reason": (
            "Nuovo cliente Puipana, richiesto da Matteo 2/10/2026: 0.5 SET "
            "ciascuna di Afila/Cilantro/Mizuna/Rabano, ogni 14 giorni. Prima "
            "consegna gia' avvenuta giovedi 1/10/2026, data_inizio=2026-10-01 "
            "cosi' il prossimo giro cade il 15/10/2026 (confermato: "
            "'puipana 14 giorni')."
        ),
        "correlation_id": "ONBOARDING-PUIPANA-2026-10-02",
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


def next_public_id(cur, table, prefix, taken):
    cur.execute(f"SELECT public_id FROM tpo.{table}")
    numbers = [int(re.fullmatch(prefix + r"-([0-9]{6,})", row[0]).group(1)) for row in cur.fetchall()]
    for already in taken:
        numbers.append(int(re.fullmatch(prefix + r"-([0-9]{6,})", already).group(1)))
    nxt = max(numbers, default=0) + 1
    pid = f"{prefix}-{nxt:06d}"
    taken.add(pid)
    return pid


conn = db()
try:
    with conn.cursor() as cur:
        taken_cli = set()
        taken_pf = set()
        for cliente in CLIENTI:
            nome = cliente["denominazione"]
            print(f"=== {nome} ===")

            cur.execute("SELECT public_id FROM tpo.clienti WHERE denominazione=%s", (nome,))
            row = cur.fetchone()
            if row:
                cli_pid = row[0]
                print(f"{nome}: CLIENTE gia' esistente ({cli_pid}). Riuso, non ricreo.")
            else:
                cli_pid = next_public_id(cur, "clienti", "CLI", taken_cli)
                run_cmd([
                    RUN, "onboarding", "customer",
                    "--customer-id", cli_pid,
                    "--denomination", nome,
                    "--actor", ACTOR,
                    "--reason", cliente["reason"],
                    "--correlation-id", cliente["correlation_id"] + "-CUSTOMER",
                ], f"onboarding customer {nome} ({cli_pid})")

            cur.execute(
                """SELECT pf.public_id FROM tpo.programmi_fornitura pf
                   JOIN tpo.clienti c ON c.id = pf.cliente_id
                   WHERE c.public_id=%s""",
                (cli_pid,),
            )
            row = cur.fetchone()
            if row:
                print(f"{nome}: PROGRAMMA_FORNITURA gia' esistente ({row[0]}). Salto.")
                print()
                continue

            pf_pid = next_public_id(cur, "programmi_fornitura", "PF", taken_pf)
            valid_from = datetime.now(timezone.utc).isoformat()
            cmd = [
                RUN, "onboarding", "supply-program",
                "--program-id", pf_pid,
                "--customer-id", cli_pid,
                "--version", "1",
                "--state", "ATTIVO",
                "--start-date", cliente["start_date"],
                "--generation-time", GENERATION_TIME,
                "--operational-window-days", str(OPERATIONAL_WINDOW_DAYS),
                "--valid-from", valid_from,
                "--actor", ACTOR,
                "--reason", cliente["reason"],
                "--correlation-id", cliente["correlation_id"] + "-PROGRAM",
            ]
            for line in cliente["lines"]:
                cmd += ["--line", line]
            run_cmd(cmd, f"onboarding supply-program {nome} ({pf_pid})")
            print()
finally:
    conn.close()

print("=== FATTO ===")
