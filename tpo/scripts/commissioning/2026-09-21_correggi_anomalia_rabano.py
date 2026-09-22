"""Correzione governata (UPDATE + audit_eventi) della nota anomalia su
LSE-000010 (Golinucci Organic, Radish Vulcano / Rabano): la nota e' solo
informativa sul metodo di verifica del residuo ("Sacco pieno/non aperto:
residuo coincide col peso di confezione originale"), non un problema di
idoneita' del seme -- stesso guardrail gia' incontrato con Afila (caso
reale, LSE_ANOMALY_BLOCKED sempre attivo su anomalia non nulla) e con
Mizuna/Hinojo (casi informativi come questo). Autorizzazione da
confermare esplicitamente da Giulia prima di eseguire questo script.
"""
import sys, json
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg
parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
ACTOR = "giulia"
REASON = ("Nota anomalia (\"Sacco pieno/non aperto: residuo coincide col peso di "
          "confezione originale\") verificata con Giulia il 21/9/2026: e' una nota sul "
          "metodo di verifica del residuo, non un problema di idoneita' del seme per uso "
          "microgreens. Anomalia rimossa per sbloccare il commissioning SEMINA reale "
          "(LSE_ANOMALY_BLOCKED); testo originale conservato in before_data.")
CORRELATION_ID = "LOTTO-SEME-CORREZIONE-2026-09-21-LSE-000010"
try:
    with conn.cursor() as cur:
        cur.execute("SELECT id, version, anomalia FROM tpo.lotti_seme WHERE public_id='LSE-000010' FOR UPDATE")
        row = cur.fetchone()
        if row is None:
            raise SystemExit("LSE-000010 non trovato.")
        internal_id, version, anomalia_prima = row
        if anomalia_prima is None:
            print("Nessuna anomalia presente, nulla da correggere.")
            raise SystemExit(0)
        now = datetime.now(timezone.utc)
        cur.execute(
            """UPDATE tpo.lotti_seme SET anomalia=NULL, updated_at=%s, updated_by=%s, version=version+1
               WHERE id=%s AND version=%s""",
            (now, ACTOR, internal_id, version),
        )
        if cur.rowcount != 1:
            raise SystemExit("Conflitto di versione, riprovare (qualcun altro ha modificato il lotto nel frattempo).")
        before = {"anomalia": anomalia_prima}
        after = {"anomalia": None}
        cur.execute(
            """INSERT INTO tpo.audit_eventi
                 (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                  before_data,after_data,correlation_id,provenance)
               VALUES (%s,%s,'LOTTO_SEME','LSE-000010','UPDATE',%s,%s::jsonb,%s::jsonb,%s,%s)""",
            (now, ACTOR, REASON, json.dumps(before), json.dumps(after), CORRELATION_ID,
             "OWNER_AUTHORIZED_CORRECTION_2026-09-21"),
        )
        conn.commit()
        print(f"OK: LSE-000010 anomalia rimossa (version {version} -> {version+1}).")
except SystemExit:
    conn.rollback()
    raise
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
