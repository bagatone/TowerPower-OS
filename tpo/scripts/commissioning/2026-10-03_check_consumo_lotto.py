"""Diagnostica di SOLA LETTURA per la migrazione 20261002_0036 (CONSUMO_LOTTO).
Va lanciata PRIMA (tabella assente: fotografia di partenza) e DOPO
l'applicazione (verifica del backfill). Non scrive nulla."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"], autocommit=True,
)
try:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('tpo.consumi_lotto')")
        has_table = cur.fetchone()[0] is not None
        print(f"tabella tpo.consumi_lotto presente: {has_table}")
        for schema in ("public", "tpo"):
            cur.execute("SELECT to_regclass(%s)", (f"{schema}.alembic_version",))
            if cur.fetchone()[0] is not None:
                cur.execute(f"SELECT version_num FROM {schema}.alembic_version")
                print(f"alembic_version ({schema}):", [r[0] for r in cur.fetchall()])

        print("\n== Per VARIETA+UNITA: carichi, scarichi, stock, consumi ==")
        consumed_join = (
            "LEFT JOIN (SELECT movimento_carico_id, SUM(quantita) AS c FROM tpo.consumi_lotto "
            "GROUP BY movimento_carico_id) k ON k.movimento_carico_id = m.id"
            if has_table else ""
        )
        consumed_expr = "COALESCE(k.c,0)" if has_table else "0"
        cur.execute(f"""
            SELECT v.public_id, v.denominazione, m.unita_misura,
                   SUM(CASE WHEN m.tipo='CARICO' THEN m.quantita ELSE 0 END) AS carichi,
                   SUM(CASE WHEN m.tipo='SCARICO' THEN m.quantita ELSE 0 END) AS scarichi,
                   SUM(CASE WHEN m.tipo='CARICO' THEN {consumed_expr} ELSE 0 END) AS consumato
            FROM tpo.movimenti_magazzino m
            JOIN tpo.varieta v ON v.id = m.varieta_id
            {consumed_join}
            GROUP BY v.public_id, v.denominazione, m.unita_misura
            ORDER BY v.public_id""")
        stock = {}
        cur2 = conn.cursor()
        cur2.execute("""SELECT v.public_id, s.unita_misura, s.disponibile
                        FROM tpo.stock s JOIN tpo.varieta v ON v.id = s.varieta_id""")
        for pid, unit, disp in cur2.fetchall():
            stock[(pid, unit)] = disp
        print("varieta | nome | unita | CARICHI | SCARICHI | consumato | STOCK")
        for pid, name, unit, carichi, scarichi, consumato in cur.fetchall():
            flag = ""
            if has_table and consumato != min(scarichi, carichi):
                flag = "  <-- backfill != min(scarichi, carichi): da guardare"
            print(f"{pid} | {name} | {unit} | {carichi} | {scarichi} | {consumato} | "
                  f"{stock.get((pid, unit))}{flag}")

        if has_table:
            print("\n== Residuo per ogni CARICO (quantita - consumato) ==")
            cur.execute("""
                SELECT m.public_id, v.public_id, m.data_movimento, m.quantita,
                       COALESCE(k.c,0) AS consumato, m.quantita - COALESCE(k.c,0) AS residuo
                FROM tpo.movimenti_magazzino m
                JOIN tpo.varieta v ON v.id = m.varieta_id
                LEFT JOIN (SELECT movimento_carico_id, SUM(quantita) AS c FROM tpo.consumi_lotto
                           GROUP BY movimento_carico_id) k ON k.movimento_carico_id = m.id
                WHERE m.tipo='CARICO'
                ORDER BY v.public_id, m.data_movimento, m.id""")
            for row in cur.fetchall():
                print(row)
            cur.execute("""SELECT tipo_consumo, COUNT(*), SUM(quantita)
                           FROM tpo.consumi_lotto GROUP BY tipo_consumo""")
            print("\nconsumi_lotto per tipo:", cur.fetchall())
finally:
    conn.close()
