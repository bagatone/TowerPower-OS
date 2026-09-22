"""Crea una NUOVA versione del protocollo di coltivazione Hinojo (attuale
PV-000005, versione 1, grammi_seme_per_set=12) con grammi_seme_per_set=10.

Autorizzato da Tower Power il 19/9/2026: "due grammi in meno non incidono
sulla qualita' del set, risparmio notevole sui costi di semente".

Gap architetturale reale: l'unico comando/application layer esistente
(application/agronomic_commissioning) valida esplicitamente
version==1 (CommissionAgronomicProtocolCommand.__post_init__) -- crea
SOLO un protocollo nuovo da zero, non sa revisionare uno gia' approvato.
Nessun 'seed-lot correct' o 'protocollo revisiona' esiste in main.py
(stesso gap noto gia' segnalato piu' volte). Fatto qui con una transazione
esplicita che replica ESATTAMENTE lo schema/i vincoli reali della tabella
tpo.protocollo_versioni (letti da migrations/versions/
20260810_0003_production_knowledge_prerequisites.py e
20260811_0005_production_planning_foundation.py) e lo stesso formato di
audit_eventi che userebbe il writer governato
(PostgreSQLAgronomicProtocolCommissioningWriter._version /  _payload):
1) chiude la versione 1 (valida_al = oggi) -- necessario perche' il
   vincolo EXCLUDE (protocollo_id, daterange) WHERE stato_approvazione=
   'APPROVATA' rifiuta range sovrapposti;
2) inserisce la versione 2, copiando INVARIATI tutti i campi della v1
   tranne grammi_seme_per_set (12 -> 10) e i campi di validita'/audit;
3) registra due audit_eventi (UPDATE sulla v1 per la chiusura, INSERT
   sulla v2), stesso schema before/after gia' usato per le correzioni
   precedenti (LSE-000001, LSE-000014).
"""
import sys, json, re
from pathlib import Path
from datetime import datetime, date, timezone
from decimal import Decimal
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
OLD_PUBLIC_ID = "PV-000005"
NEW_GRAMMI = Decimal("10")
CORRELATION_ID = "PROTOCOLLO-REVISIONE-2026-09-19-HINOJO"

COLS = (
    "id,protocollo_id,numero_versione,valida_dal,valida_al,contenuto,motivazione,evidenze,"
    "public_id,stato_approvazione,idratazione_ore,orario_semina_previsto,orario_raccolta_target,"
    "germinazione_giorni,crescita_luce_giorni,grammi_seme_per_set,resa_attesa,resa_unita_misura,"
    "granularita_produttiva,harvest_min_lead_giorni,harvest_max_lead_giorni,buffer_temporale_minuti,"
    "provenance,approvata_at,approvata_by,ritirata_at,ritirata_by,created_by"
)

try:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {COLS} FROM tpo.protocollo_versioni WHERE public_id=%s FOR UPDATE", (OLD_PUBLIC_ID,))
        row = cur.fetchone()
        if row is None:
            raise SystemExit(f"{OLD_PUBLIC_ID} non trovato.")
        v1 = dict(zip(COLS.split(","), row))
        if v1["stato_approvazione"] != "APPROVATA" or v1["valida_al"] is not None:
            raise SystemExit(f"Stato inatteso su {OLD_PUBLIC_ID}: {v1['stato_approvazione']!r}, valida_al={v1['valida_al']!r} -- fermo, verificare a mano.")
        if v1["grammi_seme_per_set"] == NEW_GRAMMI:
            print(f"{OLD_PUBLIC_ID} ha gia' grammi_seme_per_set={NEW_GRAMMI}, nulla da fare.")
            raise SystemExit(0)

        oggi = date.today()
        if oggi <= v1["valida_dal"]:
            raise SystemExit(f"Data odierna {oggi} non successiva a valida_dal {v1['valida_dal']} -- fermo.")

        cur.execute("SELECT public_id FROM tpo.protocollo_versioni WHERE public_id ~ '^PV-[0-9]{6,}$'")
        max_n = max(int(re.match(r'^PV-(\d+)$', r[0]).group(1)) for r in cur.fetchall())
        new_public_id = f"PV-{max_n + 1:06d}"

        now = datetime.now(timezone.utc)

        # 1) chiude la v1
        cur.execute(
            "UPDATE tpo.protocollo_versioni SET valida_al=%s WHERE id=%s AND public_id=%s AND valida_al IS NULL",
            (oggi, v1["id"], OLD_PUBLIC_ID),
        )
        if cur.rowcount != 1:
            raise SystemExit("Conflitto: la v1 e' stata modificata nel frattempo, riprovare.")
        cur.execute(
            """INSERT INTO tpo.audit_eventi
                 (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                  before_data,after_data,correlation_id,provenance)
               VALUES (%s,%s,'PROTOCOLLO_VERSIONE',%s,'UPDATE',%s,%s::jsonb,%s::jsonb,%s,%s)""",
            (now, ACTOR, OLD_PUBLIC_ID,
             "Chiusura versione superata da revisione grammatura seme (vedi versione successiva).",
             json.dumps({"valida_al": None}), json.dumps({"valida_al": oggi.isoformat()}),
             CORRELATION_ID, "OWNER_AUTHORIZED_PROTOCOL_REVISION_2026-09-19"),
        )

        # 2) inserisce la v2, identica alla v1 tranne grammi_seme_per_set/validita/audit
        contenuto_v2 = (
            f"hydration_hours={v1['idratazione_ore']}; germination_days={v1['germinazione_giorni']}; "
            f"light_growth_days={v1['crescita_luce_giorni']}; seed_grams_per_set={NEW_GRAMMI}"
        )
        motivazione_v2 = (
            "Revisione grammatura seme per SET da 12g a 10g: verificato che il risparmio non incide "
            "sulla qualita' del set. Autorizzato da Tower Power il 19/9/2026."
        )
        cur.execute(
            """INSERT INTO tpo.protocollo_versioni
                 (protocollo_id,numero_versione,valida_dal,valida_al,contenuto,motivazione,evidenze,
                  public_id,stato_approvazione,idratazione_ore,orario_semina_previsto,
                  orario_raccolta_target,germinazione_giorni,crescita_luce_giorni,
                  grammi_seme_per_set,resa_attesa,resa_unita_misura,granularita_produttiva,
                  harvest_min_lead_giorni,harvest_max_lead_giorni,buffer_temporale_minuti,
                  provenance,approvata_at,approvata_by,created_by,versione_precedente_id)
               VALUES (%s,%s,%s,NULL,%s,%s,%s,%s,'APPROVATA',%s,%s,%s,%s,%s,%s,%s,'SET',%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (v1["protocollo_id"], v1["numero_versione"] + 1, oggi, contenuto_v2, motivazione_v2,
             v1["evidenze"], new_public_id, v1["idratazione_ore"], v1["orario_semina_previsto"],
             v1["orario_raccolta_target"], v1["germinazione_giorni"], v1["crescita_luce_giorni"],
             NEW_GRAMMI, v1["resa_attesa"], v1["granularita_produttiva"], v1["harvest_min_lead_giorni"],
             v1["harvest_max_lead_giorni"], v1["buffer_temporale_minuti"],
             "OWNER_AUTHORIZED_PROTOCOL_REVISION_2026-09-19", now, ACTOR, ACTOR, v1["id"]),
        )
        new_id = cur.fetchone()[0]

        payload_v2 = {
            "protocollo_id": v1["protocollo_id"], "numero_versione": v1["numero_versione"] + 1,
            "valida_dal": oggi.isoformat(), "valida_al": None,
            "hydration_hours": str(v1["idratazione_ore"]),
            "planned_sowing_time": v1["orario_semina_previsto"].isoformat(),
            "target_harvest_time": v1["orario_raccolta_target"].isoformat(),
            "germination_days": v1["germinazione_giorni"], "light_growth_days": v1["crescita_luce_giorni"],
            "seed_grams_per_set": str(NEW_GRAMMI), "expected_yield": str(v1["resa_attesa"]),
            "expected_yield_uom": "SET", "production_granularity": str(v1["granularita_produttiva"]),
            "harvest_min_lead_days": v1["harvest_min_lead_giorni"], "harvest_max_lead_days": v1["harvest_max_lead_giorni"],
            "temporal_buffer_minutes": v1["buffer_temporale_minuti"],
            "provenance": "OWNER_AUTHORIZED_PROTOCOL_REVISION_2026-09-19",
            "versione_precedente_id": v1["id"], "versione_precedente_public_id": OLD_PUBLIC_ID,
        }
        cur.execute(
            """INSERT INTO tpo.audit_eventi
                 (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                  after_data,correlation_id)
               VALUES (%s,%s,'PROTOCOLLO_VERSIONE',%s,'INSERT',%s,%s::jsonb,%s)""",
            (now, ACTOR, new_public_id, motivazione_v2, json.dumps(payload_v2, sort_keys=True), CORRELATION_ID),
        )
        conn.commit()
        print(f"OK: {OLD_PUBLIC_ID} chiuso (valida_al={oggi}); nuova versione {new_public_id} "
              f"(id={new_id}) creata con grammi_seme_per_set={NEW_GRAMMI}.")
        print(f"NUOVO_PROTOCOLLO_VERSIONE={new_public_id}")
except SystemExit:
    conn.rollback()
    raise
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
