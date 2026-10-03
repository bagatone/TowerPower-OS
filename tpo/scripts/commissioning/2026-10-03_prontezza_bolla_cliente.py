"""Diagnostica di SOLA LETTURA: cosa manca per consegnare a un cliente CON la
bolla completa di codici di tracciabilita'. Uso (da cartella progetto):
    .venv/bin/python scripts/commissioning/2026-10-03_prontezza_bolla_cliente.py bahia
Mostra: ORDINI/righe del cliente (e quanto gia' consegnato), STOCK per
varieta'+unita', e per ogni SEMINA: stato, data avvio, RACCOLTE, CARICHI in
magazzino. Non scrive nulla."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

needle = f"%{sys.argv[1] if len(sys.argv) > 1 else 'bahia'}%"
parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"], autocommit=True,
)
try:
    with conn.cursor() as cur:
        cur.execute("SELECT id, public_id, denominazione FROM tpo.clienti WHERE denominazione ILIKE %s", (needle,))
        clienti = cur.fetchall()
        print("== CLIENTI trovati:", [(c[1], c[2]) for c in clienti])
        for cliente_pk, cliente_id, nome in clienti:
            print(f"\n== ORDINI di {nome} ({cliente_id})")
            cur.execute("""
                SELECT o.public_id, o.stato::text, o.data_consegna_prevista, ro.public_id,
                       v.public_id, v.denominazione, ro.quantita, ro.unita_misura::text,
                       COALESCE((SELECT SUM(rc.quantita) FROM tpo.righe_consegna rc
                                 JOIN tpo.consegne c ON c.id = rc.consegna_id
                                 WHERE rc.riga_ordine_id = ro.id AND c.stato = 'CONSEGNATA'), 0)
                FROM tpo.ordini o
                JOIN tpo.righe_ordine ro ON ro.ordine_id = o.id
                JOIN tpo.varieta v ON v.id = ro.varieta_id
                WHERE o.cliente_id = %s ORDER BY o.data_consegna_prevista, o.public_id, ro.posizione""",
                (cliente_pk,))
            rows = cur.fetchall()
            print("ordine | stato | consegna prevista | riga | varieta | nome | qta | unita | gia' consegnato")
            for r in rows:
                print(" | ".join(str(x) for x in r))
            if not rows:
                print("(nessun ORDINE per questo cliente)")

        print("\n== STOCK")
        cur.execute("""SELECT v.public_id, v.denominazione, s.unita_misura::text, s.disponibile
                       FROM tpo.stock s JOIN tpo.varieta v ON v.id = s.varieta_id
                       ORDER BY v.public_id, s.unita_misura""")
        for r in cur.fetchall():
            print(" | ".join(str(x) for x in r))

        print("\n== SEMINE con RACCOLTE e CARICHI")
        cur.execute("""
            SELECT s.public_id, s.codice_tracciabilita, v.denominazione, s.stato::text,
                   s.data_avvio::date,
                   (SELECT string_agg(r.public_id || ' ' || r.quantita::text || ' ' || r.unita_misura::text
                                      || ' (' || r.data_raccolta::date || ')', '; ' ORDER BY r.id)
                    FROM tpo.raccolte r WHERE r.semina_id = s.id) AS raccolte,
                   (SELECT string_agg(m.public_id || ' ' || m.quantita::text || ' ' || m.unita_misura::text,
                                      '; ' ORDER BY m.id)
                    FROM tpo.movimenti_magazzino m JOIN tpo.raccolte r ON r.id = m.raccolta_id
                    WHERE r.semina_id = s.id AND m.tipo = 'CARICO') AS carichi
            FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id
            ORDER BY s.data_avvio, s.public_id""")
        print("semina | codice | varieta | stato | avvio | raccolte | carichi in magazzino")
        for r in cur.fetchall():
            print(" | ".join("-" if x is None else str(x) for x in r))
finally:
    conn.close()
