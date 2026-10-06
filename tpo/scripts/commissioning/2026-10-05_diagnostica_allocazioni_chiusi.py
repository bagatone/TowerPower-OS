"""Diagnostica di SOLA LETTURA: allocazioni ATTIVE su ordini non piu' APERTO/PARZIALMENTE_EVASO (5/10/2026).
Per ognuna: tipo, quantita', residuo, riga di piano e revisione (se corrente), riga d'ordine con
ordinato/consegnato, stato ordine, sorgente (stock o raccolta) e stock attuale della varieta'. Non scrive nulla.

Uso: .venv/bin/python scripts/commissioning/2026-10-05_diagnostica_allocazioni_chiusi.py
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
print("alloc | tipo | qta | uom | residuo | riga piano (stato) | revisione (corrente?) | riga ordine | ordinato | "
      "consegnato | ordine (stato) | varieta | sorgente | stock attuale varieta")
cur.execute("""
SELECT a.public_id, a.allocation_type, a.quantity, a.unita_misura::text,
       a.quantity - COALESCE((SELECT SUM(t.quantity) FROM tpo.transizioni_allocazione t
            WHERE t.allocation_id=a.id AND t.transition_type IN ('CONSUMATA','RILASCIATA','SOSTITUITA','INVALIDA')),0),
       rps.public_id||' ('||rps.stato||')',
       pr.public_id||' ('||CASE WHEN EXISTS (SELECT 1 FROM tpo.piani_produzione pp WHERE pp.current_revision_id=pr.id)
                               THEN 'corrente' ELSE 'storica' END||')',
       ro.public_id, ro.quantita,
       COALESCE((SELECT SUM(rc.quantita) FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id
                 WHERE rc.riga_ordine_id=ro.id AND c.stato='CONSEGNATA'),0),
       o.public_id||' ('||o.stato::text||')', v.denominazione,
       COALESCE((SELECT 'STOCK '||sv.denominazione FROM tpo.allocazioni_stock ast JOIN tpo.varieta sv ON sv.id=ast.stock_varieta_id
                 WHERE ast.allocation_id=a.id),
                (SELECT 'RACCOLTA '||rac.public_id FROM tpo.allocazioni_raccolta ar JOIN tpo.raccolte rac ON rac.id=ar.raccolta_id
                 WHERE ar.allocation_id=a.id), '-'),
       (SELECT string_agg(s.unita_misura::text||' '||s.disponibile, ', ') FROM tpo.stock s WHERE s.varieta_id=v.id)
FROM tpo.allocazioni a
JOIN tpo.righe_piano_semina rps ON rps.id=a.riga_piano_semina_id
JOIN tpo.piano_produzione_revisioni pr ON pr.id=rps.piano_revisione_id
JOIN tpo.righe_ordine ro ON ro.id=rps.riga_ordine_id JOIN tpo.ordini o ON o.id=ro.ordine_id
JOIN tpo.varieta v ON v.id=ro.varieta_id
WHERE a.state='ATTIVA' AND o.stato NOT IN ('APERTO','PARZIALMENTE_EVASO')
ORDER BY a.public_id""")
rows = cur.fetchall()
for r in rows:
    print(" | ".join("-" if x is None else str(x) for x in r))
if not rows:
    print("(nessuna)")
conn.close()
