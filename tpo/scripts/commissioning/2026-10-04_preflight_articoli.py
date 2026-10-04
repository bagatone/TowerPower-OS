"""Diagnostica di SOLA LETTURA: articoli di magazzino (substrati, vaschette,
packaging...) gia' presenti nel sistema, con unita' di misura, giacenza e
ultimi movimenti. Serve a decidere se registrare un nuovo carico su un
articolo esistente o commissionarne uno nuovo. Non scrive nulla."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402
import psycopg  # noqa: E402

p = load_postgresql_parameters()
conn = psycopg.connect(
    host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
    password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"],
    autocommit=True,
)
try:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('tpo.articoli'), to_regclass('tpo.stock_articoli')")
        print("tabelle articoli/stock_articoli:", cur.fetchone())
        print("\n== ARTICOLI ==")
        cur.execute("""SELECT a.public_id, a.denominazione, a.unita_misura::text,
                              COALESCE(s.disponibile, 0), a.created_at::date
                       FROM tpo.articoli a
                       LEFT JOIN tpo.stock_articoli s ON s.articolo_id = a.id
                       ORDER BY a.public_id""")
        rows = cur.fetchall()
        print("id | denominazione | unita | giacenza | creato")
        for r in rows:
            print(" | ".join(str(x) for x in r))
        if not rows:
            print("(nessun articolo commissionato)")
        print("\n== ULTIMI MOVIMENTI ARTICOLO (max 20) ==")
        cur.execute("""SELECT m.public_id, a.public_id, a.denominazione, m.tipo::text, m.direzione::text,
                              m.quantita, m.unita_misura::text, m.data_movimento, m.motivo
                       FROM tpo.movimenti_magazzino m JOIN tpo.articoli a ON a.id = m.articolo_id
                       ORDER BY m.id DESC LIMIT 20""")
        for r in cur.fetchall():
            print(" | ".join(str(x) for x in r))
        print("\n== CONTATORE ART ==")
        cur.execute("SELECT next_value FROM tpo.id_sequences WHERE sequence_name='ARTICOLO_ID'")
        print(cur.fetchall())
finally:
    conn.close()
