"""Verifica lo stato reale del PROGRAMMA_FORNITURA di Selvaje (CLI-000004)
e, se risulta ancora ATTIVO (non gia' sospeso), applica la sospensione
richiesta da Matteo/Giulia il 18/9 (Fatto 18): ripresa prevista 9/10/2026.

Legge SEMPRE la versione corrente dal vivo un istante prima di scrivere
(mai un valore invecchiato). Idempotente: se il programma risulta gia'
SOSPESO, non fa nulla.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python scripts/commissioning/2026-09-29_verifica_sospendi_selvaje.py
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
CLIENTE_PUBLIC_ID = "CLI-000004"  # Selvaje
DATA_RIPRESA = "2026-10-09"
EFFECTIVE_AT = "2026-09-29T18:00:00+01:00"


def run_cli(cmd, label):
    print(f"--- {label} ---")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    return result.stdout


def main():
    params = load_postgresql_parameters()
    with psycopg.connect(**params) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pf.public_id, pfv.numero_versione, pfv.stato,
                       pf.data_ripresa_prevista
                FROM tpo.programmi_fornitura pf
                JOIN tpo.clienti c ON c.id = pf.cliente_id
                JOIN tpo.programmi_fornitura_versioni pfv
                  ON pfv.programma_fornitura_id = pf.id
                WHERE c.public_id = %s
                  AND pfv.valida_al IS NULL
                  AND pfv.voided_at IS NULL
                ORDER BY pfv.numero_versione DESC
                """,
                (CLIENTE_PUBLIC_ID,),
            )
            rows = cur.fetchall()

    if not rows:
        print(f"Nessun PROGRAMMA_FORNITURA corrente trovato per {CLIENTE_PUBLIC_ID}.")
        return

    if len(rows) > 1:
        print(f"ATTENZIONE: trovati {len(rows)} programmi correnti per {CLIENTE_PUBLIC_ID}, ambiguo. Nessuna azione.")
        for r in rows:
            print(r)
        return

    programma_public_id, versione, stato, data_ripresa = rows[0]
    print(
        f"Programma {programma_public_id}: versione {versione}, "
        f"stato={stato}, data_ripresa_prevista={data_ripresa}"
    )

    if stato == "SOSPESO":
        print("Gia' SOSPESO -- nessuna azione necessaria.")
        return

    print(f"Stato attuale '{stato}' != SOSPESO -- applico la sospensione richiesta il 18/9.")
    run_cli(
        [
            RUN,
            "programma-fornitura",
            "sospendi",
            "--programma", programma_public_id,
            "--expected-numero-versione", str(versione),
            "--effective-at", EFFECTIVE_AT,
            "--data-ripresa-prevista", DATA_RIPRESA,
            "--actor", "matteo",
            "--reason", "Sospensione fornitura Selvaje per calo ordini, ripresa prevista 9/10/2026 (richiesta 18/9, mai applicata nel sistema)",
            "--correlation-id", "SOSPENSIONE-SELVAJE-2026-09-29",
            "--idempotency-key", "sospendi-selvaje-2026-09-29",
            "--confirm",
        ],
        "programma-fornitura sospendi (Selvaje)",
    )


if __name__ == "__main__":
    main()
