"""Correzione governata (UPDATE + audit_eventi) della nota anomalia su
LSE-000014 (Pea Green Affila): l'etichetta fornitore dice 'FOR SPROUTS' ma
Matteo ha confermato (15/9/2026, in chat) che il seme viene usato per la
coltivazione reale di Afila come microgreens. La nota originale resta
conservata in before_data per storicita'; qui rimuoviamo solo l'anomalia
che blocca il commissioning SEMINA reale (AnomalousSeedLotError).
Nessun comando CLI esiste per questa correzione (gap noto, nessun
'seed-lot correct' in main.py) -- fatta qui con transazione esplicita e
audit_eventi manuale, stesso schema before/after usato dal resto del
sistema.
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
REASON = ("Nota anomalia 'destinato a germogli (sprouts), non microgreens' verificata "
          "con il titolare (Matteo, 15/9/2026): il seme Pea Green Affila (LSE-000014) e' "
          "lo stesso da sempre usato per coltivare Afila come microgreens; l'etichetta del "
          "fornitore riporta 'FOR SPROUTS' ma non riflette l'uso reale in azienda. Anomalia "
          "rimossa per sbloccare il commissioning SEMINA reale; testo originale conservato "
          "in before_data.")
CORRELATION_ID = "LOTTO-SEME-CORREZIONE-2026-09-15-LSE-000014"
try:
    with conn.cursor() as cur:
        cur.execute("SELECT id, version, anomalia FROM tpo.lotti_seme WHERE public_id='LSE-000014' FOR UPDATE")
        row = cur.fetchone()
        if row is None:
            raise SystemExit("LSE-000014 non trovato.")
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
               VALUES (%s,%s,'LOTTO_SEME','LSE-000014','UPDATE',%s,%s::jsonb,%s::jsonb,%s,%s)""",
            (now, ACTOR, REASON, json.dumps(before), json.dumps(after), CORRELATION_ID,
             "OWNER_AUTHORIZED_CORRECTION_2026-09-15"),
        )
        conn.commit()
        print(f"OK: LSE-000014 anomalia rimossa (version {version} -> {version+1}).")
except SystemExit:
    conn.rollback()
    raise
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
