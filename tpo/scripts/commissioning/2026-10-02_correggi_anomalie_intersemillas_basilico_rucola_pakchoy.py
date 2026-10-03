"""Correzione governata (UPDATE + audit_eventi) della nota anomalia su
LSE-000003 (Albahaca/Basilico), LSE-000004 (Rucula/Rucola) e LSE-000006
(Pak Choi) -- tutte Intersemillas. In tutti e tre i casi la nota e' solo
informativa (data di analisi Giugno 2026 in etichetta scambiabile per
scadenza, nome botanico presunto, codice operatore ES17461319), stesso
genere di caso gia' visto e corretto per LSE-000001 (Mizuna, 17/9),
LSE-000005 (Hinojo, 19/9), LSE-000019 (Rabano Hyfarm, 21/9) -- non un
problema di idoneita' del seme per uso microgreens. Stesso guardrail di
sistema (AnomalousSeedLotError / LSE_ANOMALY_BLOCKED) blocca qualsiasi
lotto con anomalia non nulla, indipendentemente dal contenuto.

Autorizzato esplicitamente da Matteo (Tower Power) il 2/10/2026, dopo
aver verificato i dati reali (2026-10-02_check_lotti_intersemillas_
basilico_rucola_pakchoy.py) e avergli mostrato il parallelo con i casi
precedenti. Nessun comando CLI esiste per questa correzione (gap noto,
nessun 'seed-lot correct' in main.py) -- fatta qui con transazione
esplicita e audit_eventi manuale, stesso schema before/after usato nei
precedenti.

Idempotente: se l'anomalia e' gia' NULL per un lotto, lo salta.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python3 scripts/commissioning/2026-10-02_correggi_anomalie_intersemillas_basilico_rucola_pakchoy.py
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

ACTOR = "matteo"
LOTTI = [
    {
        "lse": "LSE-000003",
        "nome": "Basilico (Albahaca)",
        "reason": (
            "Nota anomalia (data di analisi Giugno 2026 in etichetta scambiabile per "
            "scadenza; nome botanico presunto Ocimum basilicum, non riportato in "
            "etichetta; codice operatore ES17461319) verificata: e' una nota "
            "informativa sull'etichetta, non un problema di idoneita' del seme per "
            "uso microgreens. Anomalia rimossa per sbloccare il commissioning SEMINA "
            "reale (LSE_ANOMALY_BLOCKED); testo originale conservato in before_data."
        ),
    },
    {
        "lse": "LSE-000004",
        "nome": "Rucola (Rucula)",
        "reason": (
            "Nota anomalia (data di analisi Giugno 2026 in etichetta scambiabile per "
            "scadenza; nome botanico presunto Eruca sativa; codice operatore "
            "ES17461319) verificata: e' una nota informativa sull'etichetta, non un "
            "problema di idoneita' del seme per uso microgreens. Anomalia rimossa per "
            "sbloccare il commissioning SEMINA reale (LSE_ANOMALY_BLOCKED); testo "
            "originale conservato in before_data."
        ),
    },
    {
        "lse": "LSE-000006",
        "nome": "Pak Choi",
        "reason": (
            "Nota anomalia (data di analisi Giugno 2026 in etichetta scambiabile per "
            "scadenza; nome botanico presunto Brassica rapa chinensis; codice "
            "operatore ES17461319) verificata: e' una nota informativa sull'etichetta, "
            "non un problema di idoneita' del seme per uso microgreens. Anomalia "
            "rimossa per sbloccare il commissioning SEMINA reale (LSE_ANOMALY_BLOCKED); "
            "testo originale conservato in before_data."
        ),
    },
]

parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
try:
    for lotto in LOTTI:
        lse_pid = lotto["lse"]
        print(f"=== {lotto['nome']} ({lse_pid}) ===")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, version, anomalia FROM tpo.lotti_seme WHERE public_id=%s FOR UPDATE",
                    (lse_pid,),
                )
                row = cur.fetchone()
                if row is None:
                    raise SystemExit(f"{lse_pid} non trovato.")
                internal_id, version, anomalia_prima = row
                if anomalia_prima is None:
                    print(f"{lse_pid}: nessuna anomalia presente, nulla da correggere.")
                    conn.rollback()
                    continue
                now = datetime.now(timezone.utc)
                cur.execute(
                    """UPDATE tpo.lotti_seme SET anomalia=NULL, updated_at=%s, updated_by=%s, version=version+1
                       WHERE id=%s AND version=%s""",
                    (now, ACTOR, internal_id, version),
                )
                if cur.rowcount != 1:
                    raise SystemExit(f"{lse_pid}: conflitto di versione, riprovare.")
                before = {"anomalia": anomalia_prima}
                after = {"anomalia": None}
                correlation_id = f"LOTTO-SEME-CORREZIONE-2026-10-02-{lse_pid}"
                cur.execute(
                    """INSERT INTO tpo.audit_eventi
                         (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                          before_data,after_data,correlation_id,provenance)
                       VALUES (%s,%s,'LOTTO_SEME',%s,'UPDATE',%s,%s::jsonb,%s::jsonb,%s,%s)""",
                    (now, ACTOR, lse_pid, lotto["reason"], json.dumps(before), json.dumps(after),
                     correlation_id, "OWNER_AUTHORIZED_CORRECTION_2026-10-02"),
                )
                conn.commit()
                print(f"OK: {lse_pid} anomalia rimossa (version {version} -> {version + 1}).")
        except SystemExit as exc:
            conn.rollback()
            print(f"FERMO per {lse_pid}: {exc}")
        print()
finally:
    conn.close()

print("=== FATTO ===")
