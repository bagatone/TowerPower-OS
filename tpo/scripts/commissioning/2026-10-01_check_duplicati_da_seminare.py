"""Diagnostica di sola lettura: Matteo ha mandato uno screenshot del
Rendiconto Mattutino ("Da seminare oggi") con piu' righe ripetute per la
stessa coppia cliente+varieta' (es. "Hinojo per Alchimia Sushi" x3), e alcune
a quantita' 0.000000 SET -- qui controlliamo riga per riga cosa c'e' davvero
dietro, SENZA scrivere nulla: ogni riga_piano_semina e' una vera riga di
piano distinta o e' un bug di duplicazione? Stesso filtro di data usato dal
rendiconto (rps.sowing_at::date <= oggi, quindi include anche l'arretrato
di giorni precedenti non ancora seminato, non solo oggi)."""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

OFFICIAL_TIMEZONE = ZoneInfo("Atlantic/Canary")
oggi = datetime.now(OFFICIAL_TIMEZONE).date()

parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
try:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT rps.public_id, v.denominazione, c.denominazione, rps.stato,
                      rps.quantita_residua_da_avviare, rps.unita_domanda, rps.sowing_at,
                      o.public_id, ro.id, rps.piano_revisione_id
               FROM tpo.righe_piano_semina rps
               JOIN tpo.varieta v ON v.id = rps.varieta_id
               JOIN tpo.piano_produzione_revisioni pr ON pr.id = rps.piano_revisione_id
               JOIN tpo.righe_ordine ro ON ro.id = rps.riga_ordine_id
               JOIN tpo.ordini o ON o.id = ro.ordine_id
               JOIN tpo.clienti c ON c.id = o.cliente_id
               WHERE pr.sostituita_at IS NULL AND rps.stato IN ('PIANIFICATA','PRONTA','TARDIVA')
                 AND rps.sowing_at::date <= %s
               ORDER BY c.denominazione, v.denominazione, rps.sowing_at""",
            (oggi,),
        )
        rows = cur.fetchall()
    print(f"Oggi (Atlantic/Canary): {oggi}")
    print(f"{len(rows)} righe totali in 'da seminare' (oggi + arretrato)\n")
    gruppi: dict[tuple[str, str], list] = {}
    for r in rows:
        gruppi.setdefault((r[2], r[1]), []).append(r)
    for (cliente, varieta), righe in gruppi.items():
        tag = " <-- GRUPPO con piu' righe" if len(righe) > 1 else ""
        print(f"{varieta} per {cliente}: {len(righe)} riga/he{tag}")
        for (pid, _v, _c, stato, qta, uom, sowing_at, ord_pid, riga_ordine_id, piano_rev_id) in righe:
            flag = " *** QUANTITA' ZERO -- non dovrebbe comparire da seminare ***" if qta == 0 else ""
            print(
                f"    {pid} stato={stato} residuo={qta}{uom.lower()} "
                f"sowing_at={sowing_at:%Y-%m-%d %H:%M} ordine={ord_pid} "
                f"riga_ordine_id={riga_ordine_id} piano_revisione_id={piano_rev_id}{flag}"
            )
finally:
    conn.close()
