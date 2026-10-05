"""Diagnostica di SOLA LETTURA per il replanning delle allocazioni obsolete (5/10/2026).
Per OGNI allocazione ATTIVA di tipo STOCK mostra: allocazione (versione, quantita', residuo,
transizioni gia' fatte), riga del piano e revisione (se e' quella corrente), riga d'ordine,
ordine (stato), cliente, stock attuale della varieta'. Mostra anche i piani correnti e i
disposition set gia' esistenti. Non scrive nulla.

Uso: .venv/bin/python scripts/commissioning/2026-10-05_diagnostica_replanning.py
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


show("ALLOCAZIONI STOCK ATTIVE",
     "alloc | ver | tipo | qta | uom | residuo | transizioni | riga piano | stato riga | revisione | corrente? | "
     "riga ordine | qta riga | ordine | stato ordine | prevista | cliente | varieta | stock disp.",
     """
SELECT a.public_id, a.version, a.allocation_type, a.quantity, a.unita_misura::text,
       a.quantity - COALESCE((SELECT SUM(t.quantity) FROM tpo.transizioni_allocazione t
            WHERE t.allocation_id=a.id AND t.transition_type IN ('CONSUMATA','RILASCIATA','SOSTITUITA','INVALIDA')),0),
       (SELECT string_agg(t.transition_type||' '||t.quantity, ', ') FROM tpo.transizioni_allocazione t
            WHERE t.allocation_id=a.id),
       rps.public_id, rps.stato, pr.public_id,
       CASE WHEN EXISTS (SELECT 1 FROM tpo.piani_produzione pp WHERE pp.current_revision_id=pr.id) THEN 'SI' ELSE 'no' END,
       ro.public_id, ro.quantita, o.public_id, o.stato::text, o.data_consegna_prevista, cl.denominazione,
       v.denominazione, (SELECT string_agg(s.unita_misura::text||' '||s.disponibile, ', ')
            FROM tpo.stock s WHERE s.varieta_id=v.id)
FROM tpo.allocazioni a
JOIN tpo.righe_piano_semina rps ON rps.id=a.riga_piano_semina_id
JOIN tpo.piano_produzione_revisioni pr ON pr.id=rps.piano_revisione_id
JOIN tpo.righe_ordine ro ON ro.id=rps.riga_ordine_id
JOIN tpo.ordini o ON o.id=ro.ordine_id
JOIN tpo.clienti cl ON cl.id=o.cliente_id
JOIN tpo.varieta v ON v.id=ro.varieta_id
WHERE a.state='ATTIVA' AND a.allocation_type='STOCK'
ORDER BY a.public_id""")

show("PIANI CORRENTI", "piano | versione | revisione corrente | numero revisione | righe",
     """SELECT p.public_id, p.version, r.public_id, r.numero_revisione,
               (SELECT count(*) FROM tpo.righe_piano_semina l WHERE l.piano_revisione_id=r.id)
        FROM tpo.piani_produzione p JOIN tpo.piano_produzione_revisioni r ON r.id=p.current_revision_id
        ORDER BY p.public_id""")

show("DISPOSITION SET gia' esistenti", "id | stato | revisione | riga ordine | motivo | correlation",
     """SELECT s.id, s.state, pr.public_id, ro.public_id, s.replanning_reason_code, s.correlation_id
        FROM tpo.replanning_disposition_sets s
        JOIN tpo.piano_produzione_revisioni pr ON pr.id=s.previous_plan_revision_id
        JOIN tpo.righe_ordine ro ON ro.id=s.order_line_id ORDER BY s.id""")

show("ULTIMI RUN DI PIANIFICAZIONE", "run | stato | business_at | avviato",
     """SELECT public_id, state, business_at, started_at::timestamp(0)
        FROM tpo.production_planning_runs ORDER BY id DESC LIMIT 6""")
