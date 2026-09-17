"""Correzione governata (UPDATE + audit_eventi) della nota anomalia su
LSE-000001 (Golinucci Organic, Mizuna Red): la nota era solo informativa
sul metodo di misurazione del residuo (230g+550g dichiarati a voce dal
titolare su un sacco originale da 1kg), non un problema di idoneita' del
seme -- diverso dal caso Afila (LSE-000014, 15/9/2026), ma stesso guardrail
di sistema (AnomalousSeedLotError / LSE_ANOMALY_BLOCKED) blocca QUALSIASI
lotto con anomalia non nulla, indipendentemente dal contenuto. Autorizzato
esplicitamente da Giulia (Tower Power) il 17/9/2026. Nessun comando CLI
esiste per questa correzione (gap noto, nessun 'seed-lot correct' in
main.py) -- fatta qui con transazione esplicita e audit_eventi manuale,
stesso schema before/after usato per LSE-000014.
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
REASON = ("Nota anomalia (residuo 780g dichiarato a voce come somma di due misurazioni, "
          "230g+550g, su sacco originale da 1kg) verificata con il titolare (Giulia, "
          "17/9/2026): e' una nota sul metodo di misurazione del residuo, non un problema "
          "di idoneita' del seme per uso microgreens. Anomalia rimossa per sbloccare il "
          "commissioning SEMINA reale (LSE_ANOMALY_BLOCKED); testo originale conservato "
          "in before_data.")
CORRELATION_ID = "LOTTO-SEME-CORREZIONE-2026-09-17-LSE-000001"
try:
    with conn.cursor() as cur:
        cur.execute("SELECT id, version, anomalia FROM tpo.lotti_seme WHERE public_id='LSE-000001' FOR UPDATE")
        row = cur.fetchone()
        if row is None:
            raise SystemExit("LSE-000001 non trovato.")
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
               VALUES (%s,%s,'LOTTO_SEME','LSE-000001','UPDATE',%s,%s::jsonb,%s::jsonb,%s,%s)""",
            (now, ACTOR, REASON, json.dumps(before), json.dumps(after), CORRELATION_ID,
             "OWNER_AUTHORIZED_CORRECTION_2026-09-17"),
        )
        conn.commit()
        print(f"OK: LSE-000001 anomalia rimossa (version {version} -> {version+1}).")
except SystemExit:
    conn.rollback()
    raise
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
