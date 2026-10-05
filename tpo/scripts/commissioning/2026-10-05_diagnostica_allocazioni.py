"""Diagnostica di SOLA LETTURA: perche' il piano di produzione fallisce con
RESOURCE_OVERALLOCATED ("Risorsa sovra-allocata", RPP-000006 del 2/10 e
RPP-000008 del 4/10). Ricalcola per ogni risorsa (giacenza, produzione in corso,
raccolta) quanto e' disponibile e quanto e' gia' allocato dalle allocazioni ATTIVE
del piano precedente, e mostra le risorse in cui allocato > disponibile.
Non scrive nulla.

Uso: .venv/bin/python scripts/commissioning/2026-10-05_diagnostica_allocazioni.py
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

# allocazioni ATTIVE non DOMANDA con residuo, per risorsa (stessa logica del motore)
ALLOC = """
WITH al AS (
  SELECT a.id, a.public_id, a.allocation_type AS tipo, a.state,
         COALESCE(vs.public_id, sem.public_id, rac.public_id) AS risorsa,
         ro.public_id AS riga, a.quantity, a.unita_misura::text AS uom,
         a.quantity - COALESCE((SELECT SUM(t.quantity) FROM tpo.transizioni_allocazione t
              WHERE t.allocation_id=a.id AND t.transition_type IN ('CONSUMATA','RILASCIATA','SOSTITUITA','INVALIDA')),0) AS residuo
  FROM tpo.allocazioni a
  JOIN tpo.righe_piano_semina rps ON rps.id=a.riga_piano_semina_id
  JOIN tpo.righe_ordine ro ON ro.id=rps.riga_ordine_id
  LEFT JOIN tpo.allocazioni_stock ast ON ast.allocation_id=a.id
  LEFT JOIN tpo.stock st ON st.varieta_id=ast.stock_varieta_id AND st.unita_misura=ast.stock_unita_misura
  LEFT JOIN tpo.varieta vs ON vs.id=st.varieta_id
  LEFT JOIN tpo.allocazioni_produzione_in_corso aip ON aip.allocation_id=a.id
  LEFT JOIN tpo.semine sem ON sem.id=aip.semina_id
  LEFT JOIN tpo.allocazioni_raccolta ar ON ar.allocation_id=a.id
  LEFT JOIN tpo.raccolte rac ON rac.id=ar.raccolta_id
  WHERE a.state='ATTIVA' AND a.allocation_type <> 'DOMANDA')
"""
print("== ALLOCAZIONI ATTIVE per tipo")
cur.execute(ALLOC + "SELECT tipo, count(*), sum(residuo) FROM al GROUP BY 1 ORDER BY 1")
for r in cur.fetchall():
    print(" | ".join(str(x) for x in r))

print("\n== STOCK: disponibile vs allocato (da piano precedente)")
cur.execute(ALLOC + """
SELECT v.public_id, v.denominazione, s.unita_misura::text, s.disponibile,
       COALESCE((SELECT sum(residuo) FROM al WHERE tipo='STOCK' AND risorsa=v.public_id),0)
FROM tpo.stock s JOIN tpo.varieta v ON v.id=s.varieta_id ORDER BY v.public_id, s.unita_misura""")
print("varieta | nome | unita | disponibile | allocato | ESITO")
for r in cur.fetchall():
    print(" | ".join(str(x) for x in r) + (" | SOVRA-ALLOCATA" if r[4] > r[3] and r[3] > 0 or (r[4] > 0 and r[3] == 0) else " | ok"))

print("\n== PRODUZIONE IN CORSO: attesa utile vs allocato (semine non chiuse)")
cur.execute(ALLOC + """
SELECT s.public_id, v.denominazione, s.stato::text, s.expected_useful_quantity, s.expected_useful_uom::text,
       COALESCE((SELECT sum(residuo) FROM al WHERE tipo='PRODUZIONE_IN_CORSO' AND risorsa=s.public_id),0)
FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
WHERE s.stato <> 'CHIUSA' AND s.expected_useful_quantity IS NOT NULL ORDER BY s.public_id""")
print("semina | nome | stato | attesa utile | unita | allocato | ESITO")
for r in cur.fetchall():
    print(" | ".join(str(x) for x in r) + (" | SOVRA-ALLOCATA" if r[5] > r[3] else " | ok"))

print("\n== ALLOCAZIONI ATTIVE su risorse che NON sono piu' nell'elenco (semine chiuse / senza attesa utile)")
cur.execute(ALLOC + """
SELECT al.public_id, al.tipo, al.risorsa, al.riga, al.residuo, al.uom
FROM al LEFT JOIN tpo.semine s ON s.public_id=al.risorsa AND al.tipo='PRODUZIONE_IN_CORSO'
WHERE al.tipo='PRODUZIONE_IN_CORSO' AND (s.id IS NULL OR s.stato='CHIUSA' OR s.expected_useful_quantity IS NULL)""")
rows = cur.fetchall()
for r in rows:
    print(" | ".join(str(x) for x in r))
if not rows:
    print("(nessuna)")

print("\n== RACCOLTE: quantita vs allocato")
cur.execute(ALLOC + """
SELECT r.public_id, r.quantita, r.unita_misura::text,
       COALESCE((SELECT sum(residuo) FROM al WHERE tipo='RACCOLTA' AND risorsa=r.public_id),0)
FROM tpo.raccolte r ORDER BY r.public_id""")
for r in cur.fetchall():
    print(" | ".join(str(x) for x in r) + (" | SOVRA-ALLOCATA" if r[3] > r[1] else " | ok"))
conn.close()
