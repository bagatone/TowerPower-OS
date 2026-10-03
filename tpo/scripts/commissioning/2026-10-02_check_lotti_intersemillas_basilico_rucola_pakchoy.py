"""Diagnostica di sola lettura: perche' il lotto Intersemillas di Basilico
(LSE-000003) risulta senza scorta sufficiente nonostante il catalogo
dicesse 850g residui. Controlla anomalia/scadenza/residuo reali per i 3
lotti Intersemillas coinvolti (Basilico/Rucola/Pak Choi), stesso schema
usato per la verifica Hinojo del 19/9 -- niente azioni, solo dati veri."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

p = load_postgresql_parameters()
conn = psycopg.connect(
    host=p["host"], port=p["port"], dbname=p["dbname"],
    user=p["user"], password=p["password"], sslmode=p["sslmode"],
    connect_timeout=p["connect_timeout"],
)
try:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT l.public_id, s.fornitore, s.referenza_commerciale,
                      l.quantita_residua, l.unita_misura, l.data_ricezione,
                      l.data_scadenza, l.anomalia, l.version
               FROM tpo.lotti_seme l JOIN tpo.sementi s ON s.id = l.semente_id
               WHERE l.public_id IN ('LSE-000003', 'LSE-000004', 'LSE-000006')
               ORDER BY l.public_id"""
        )
        for row in cur.fetchall():
            print(row)
finally:
    conn.close()
