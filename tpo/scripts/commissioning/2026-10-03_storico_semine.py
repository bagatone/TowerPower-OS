"""Diagnostica di SOLA LETTURA: per ogni SEMINA (o solo quelle di una varieta')
data di semina, transizioni di stato registrate (con data effettiva e motivo,
cosi' si vede se una data e' un'osservazione reale o amministrativa), raccolte
e carichi. Uso:  .venv/bin/python scripts/commissioning/2026-10-03_storico_semine.py afila"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

needle = f"%{sys.argv[1]}%" if len(sys.argv) > 1 else "%"
parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"], autocommit=True,
)
try:
    with conn.cursor() as cur:
        cur.execute("""SELECT s.id, s.public_id, s.codice_tracciabilita, v.denominazione,
                              s.stato::text, s.data_avvio, s.quantita_seme
                       FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id
                       WHERE v.denominazione ILIKE %s ORDER BY v.denominazione, s.data_avvio""",
                    (needle,))
        for sid, pid, codice, nome, stato, avvio, seme in cur.fetchall():
            print(f"\n== {pid} {codice} {nome} | stato {stato} | semina {avvio:%Y-%m-%d %H:%M} | seme {seme} g")
            cur.execute("""SELECT from_state::text, to_state::text, effective_at, recorded_at, actor, reason
                           FROM tpo.semina_lifecycle_eventi WHERE semina_id = %s ORDER BY effective_at, id""",
                        (sid,))
            for fs, ts, eff, rec, actor, reason in cur.fetchall():
                print(f"   transizione {fs} -> {ts} | effettiva {eff:%Y-%m-%d %H:%M} | registrata {rec:%Y-%m-%d %H:%M} | {actor} | {reason[:90]}")
            cur.execute("""SELECT public_id, data_raccolta, quantita, unita_misura::text
                           FROM tpo.raccolte WHERE semina_id = %s ORDER BY data_raccolta""", (sid,))
            for rid, dr, q, u in cur.fetchall():
                print(f"   raccolta {rid} | {dr:%Y-%m-%d %H:%M} | {q} {u}")
finally:
    conn.close()
