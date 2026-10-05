"""Diagnostica di SOLA LETTURA delle RACCOLTE e delle allocazioni RACCOLTA attive (5/10/2026).
Per ogni raccolta: varieta', semina, data, quantita', quantita' caricata a magazzino (CARICO),
allocazioni attive (ordine, stato dell'ordine, quantita') e stock attuale della varieta'.
Non scrive nulla.

Uso: .venv/bin/python scripts/commissioning/2026-10-05_diagnostica_raccolte.py
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
print("raccolta | varieta | semina (stato) | data raccolta | quantita | caricato a stock | "
      "allocazioni ATTIVE (alloc: qta -> ordine [stato ordine, consegna prevista]) | stock attuale varieta")
cur.execute("""
SELECT rc.public_id, v.denominazione, s.public_id||' ('||s.stato::text||')', rc.data_raccolta::date,
       rc.quantita||' '||rc.unita_misura::text,
       COALESCE((SELECT SUM(m.quantita) FROM tpo.movimenti_magazzino m WHERE m.raccolta_id=rc.id
                 AND m.tipo='CARICO' AND m.unita_misura=rc.unita_misura),0),
       (SELECT string_agg(a.public_id||': '||(a.quantity - COALESCE((SELECT SUM(t.quantity)
                   FROM tpo.transizioni_allocazione t WHERE t.allocation_id=a.id),0))||' -> '||o.public_id||
                   ' ['||o.stato::text||', '||COALESCE(o.data_consegna_prevista::text,'-')||']', '; ' ORDER BY a.public_id)
        FROM tpo.allocazioni_raccolta ar JOIN tpo.allocazioni a ON a.id=ar.allocation_id AND a.state='ATTIVA'
        JOIN tpo.righe_piano_semina l ON l.id=a.riga_piano_semina_id
        JOIN tpo.righe_ordine ro ON ro.id=l.riga_ordine_id JOIN tpo.ordini o ON o.id=ro.ordine_id
        WHERE ar.raccolta_id=rc.id),
       (SELECT string_agg(st.unita_misura::text||' '||st.disponibile, ', ') FROM tpo.stock st WHERE st.varieta_id=v.id)
FROM tpo.raccolte rc JOIN tpo.semine s ON s.id=rc.semina_id JOIN tpo.varieta v ON v.id=s.varieta_id
ORDER BY rc.public_id""")
for r in cur.fetchall():
    print(" | ".join("-" if x is None else str(x) for x in r))
conn.close()
