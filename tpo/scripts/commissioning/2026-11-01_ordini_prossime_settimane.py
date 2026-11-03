"""SOLA LETTURA - ordini aperti con consegna dal 4/11 in poi, per settimana di consegna (1/11/2026).

Serve a capire cosa seminare OGGI (domenica) per le consegne della settimana del 9-15/11 e oltre: quali ordini ci sono
gia' a sistema e quali programmi ricorrenti non hanno ancora un ordine per quelle date. Non scrive nulla.

Uso: .venv/bin/python scripts/commissioning/2026-11-01_ordini_prossime_settimane.py [--dal 2026-11-04]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402
import psycopg  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--dal", default="2026-11-04")
a = ap.parse_args()

p = load_postgresql_parameters()
conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                       sslmode=p["sslmode"], connect_timeout=p["connect_timeout"], autocommit=True)
cur = conn.cursor()

print(f"== ORDINI APERTI con consegna dal {a.dal} (consegna | ordine | cliente | programma | righe: varieta SET)")
cur.execute("""
SELECT o.data_consegna_prevista, o.public_id, cl.denominazione, COALESCE(pf.public_id, 'manuale'),
       (SELECT string_agg(v.denominazione||' '||ro.quantita||' '||ro.unita_misura::text, '; ' ORDER BY ro.posizione)
          FROM tpo.righe_ordine ro JOIN tpo.varieta v ON v.id=ro.varieta_id WHERE ro.ordine_id=o.id)
FROM tpo.ordini o JOIN tpo.clienti cl ON cl.id=o.cliente_id
LEFT JOIN tpo.programmi_fornitura pf ON pf.id=o.programma_fornitura_id
WHERE o.stato IN ('APERTO','PARZIALMENTE_EVASO') AND o.data_consegna_prevista >= %s
ORDER BY o.data_consegna_prevista, cl.denominazione""", (a.dal,))
rows = cur.fetchall()
corrente = None
for d, ordine, cliente, prog, righe in rows:
    sett = d.isocalendar()[1]
    if sett != corrente:
        corrente = sett
        print(f"\n-- settimana {sett}")
    print(f"{d} ({d:%a}) | {ordine} | {cliente} | {prog} | {righe}")
if not rows:
    print("(nessun ordine)")

print("\n== PROGRAMMI DI FORNITURA: ultimo ordine aperto a sistema (programma | cliente | stato | ultimo ordine aperto)")
cur.execute("""
SELECT pf.public_id, cl.denominazione,
       (SELECT stato::text FROM tpo.programmi_fornitura_versioni v WHERE v.programma_fornitura_id=pf.id ORDER BY numero_versione DESC LIMIT 1),
       max(o.data_consegna_prevista) FILTER (WHERE o.stato IN ('APERTO','PARZIALMENTE_EVASO'))
FROM tpo.programmi_fornitura pf JOIN tpo.clienti cl ON cl.id=pf.cliente_id
LEFT JOIN tpo.ordini o ON o.programma_fornitura_id=pf.id
GROUP BY pf.id, pf.public_id, cl.denominazione ORDER BY 2""")
for r in cur.fetchall():
    print(" | ".join("-" if x is None else str(x) for x in r))
