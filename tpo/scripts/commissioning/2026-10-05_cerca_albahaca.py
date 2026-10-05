"""Ricerca di SOLA LETTURA: dove sono i SET di Albahaca/Basilico in luce?
Mostra le varieta' con nome simile, TUTTE le semine (anche chiuse) di quelle varieta'
o con codice ALB-*, tutte le semine in LUCE/CRESCITA/PRONTA di qualsiasi varieta',
lo stock e le raccolte di basilico. Non scrive nulla.

Uso: .venv/bin/python scripts/commissioning/2026-10-05_cerca_albahaca.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402
import psycopg  # noqa: E402

p = load_postgresql_parameters()
conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                       password=p["password"], sslmode=p["sslmode"],
                       connect_timeout=p["connect_timeout"], autocommit=True)
cur = conn.cursor()


def show(title, header, sql):
    print(f"\n== {title}")
    print(header)
    cur.execute(sql)
    rows = cur.fetchall()
    for r in rows:
        print(" | ".join("" if x is None else str(x) for x in r))
    if not rows:
        print("(nessuna riga)")


show("VARIETA con nome simile a basilico/albahaca", "id | nome | stato",
     "SELECT public_id, denominazione, stato::text FROM tpo.varieta "
     "WHERE denominazione ILIKE ANY (ARRAY['%alba%','%basil%','%alb%']) OR public_id='VAR-000006'")

show("SEMINE di basilico (ogni stato) o con codice ALB-*",
     "semina | codice | varieta | stato | avvio | gram seme | ultimo evento lifecycle",
     """SELECT s.public_id, s.codice_tracciabilita, v.denominazione, s.stato::text, s.data_avvio::date,
               s.quantita_seme,
               (SELECT max(e.effective_at) FROM tpo.semina_lifecycle_eventi e WHERE e.semina_id=s.id)
        FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
        WHERE v.public_id='VAR-000006' OR s.codice_tracciabilita LIKE 'ALB-%'
        ORDER BY s.public_id""")

show("SEMINE in LUCE / CRESCITA / PRONTA (qualsiasi varieta')",
     "semina | codice | varieta | stato | avvio | ultimo evento lifecycle",
     """SELECT s.public_id, s.codice_tracciabilita, v.denominazione, s.stato::text, s.data_avvio::date,
               (SELECT max(e.effective_at) FROM tpo.semina_lifecycle_eventi e WHERE e.semina_id=s.id)
        FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
        WHERE s.stato IN ('LUCE','CRESCITA','PRONTA_ALLA_RACCOLTA') ORDER BY v.denominazione, s.public_id""")

show("SEMINE avviate dal 25/09 in poi (tutte, per vedere se manca una registrazione)",
     "semina | codice | varieta | stato | avvio | creata il",
     """SELECT s.public_id, s.codice_tracciabilita, v.denominazione, s.stato::text, s.data_avvio::date, s.created_at::date
        FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
        WHERE s.data_avvio >= '2026-09-25' ORDER BY s.data_avvio, s.public_id""")

show("RACCOLTE di basilico", "raccolta | semina | data | quantita",
     """SELECT r.public_id, s.public_id, r.data_raccolta::date, r.quantita
        FROM tpo.raccolte r JOIN tpo.semine s ON s.id=r.semina_id
        WHERE s.codice_tracciabilita LIKE 'ALB-%' ORDER BY r.public_id""")

show("STOCK basilico", "varieta | nome | unita | disponibile",
     """SELECT v.public_id, v.denominazione, st.unita_misura::text, st.disponibile
        FROM tpo.stock st JOIN tpo.varieta v ON v.id=st.varieta_id WHERE v.public_id='VAR-000006'""")
