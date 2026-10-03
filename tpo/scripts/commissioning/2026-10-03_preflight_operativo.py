"""Diagnostica di SOLA LETTURA per il passaggio operativo del 3/10/2026
(pulizia giacenza, raccolte, ordini manuali, consegne e bolle di lunedi').
Uso (da cartella progetto):
    .venv/bin/python scripts/commissioning/2026-10-03_preflight_operativo.py
Mostra: VARIETA (id, nome), SEMINE operative con versione e stato, STOCK, CLIENTI
interessati (Bahia, Puipana, Alchimia, Gustavo, Selvaje), ORDINI aperti di Bahia,
contatori id_sequences vs massimo reale (ORDINE_ID, RIGA_ORDINE_ID, MOVIMENTO_ID,
CONSEGNA_ID) e revisione alembic. Non scrive nulla."""
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


def show(title, rows, header=None):
    print(f"\n== {title}")
    if header:
        print(header)
    for r in rows:
        print(" | ".join("-" if x is None else str(x) for x in r))
    if not rows:
        print("(nessuna riga)")


try:
    with conn.cursor() as cur:
        cur.execute("SELECT version_num FROM public.alembic_version")
        print("alembic:", cur.fetchall())
        cur.execute("""SELECT public_id, denominazione, stato::text FROM tpo.varieta ORDER BY public_id""")
        show("VARIETA", cur.fetchall(), "id | nome | stato")
        cur.execute("""SELECT s.public_id, s.codice_tracciabilita, v.public_id, v.denominazione,
                              s.stato::text, s.version, s.data_avvio::date
                       FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id
                       WHERE s.stato <> 'CHIUSA' ORDER BY s.public_id""")
        show("SEMINE non chiuse", cur.fetchall(), "semina | codice | varieta | nome | stato | VERSIONE | avvio")
        cur.execute("""SELECT v.public_id, v.denominazione, s.unita_misura::text, s.disponibile
                       FROM tpo.stock s JOIN tpo.varieta v ON v.id = s.varieta_id
                       ORDER BY v.public_id, s.unita_misura""")
        show("STOCK", cur.fetchall(), "varieta | nome | unita | disponibile")
        cur.execute("""SELECT public_id, denominazione FROM tpo.clienti
                       WHERE denominazione ILIKE ANY (ARRAY['%bahia%','%puipana%','%alchimia%',
                             '%gustavo%','%mamma%','%selvaje%','%salvaje%']) ORDER BY public_id""")
        show("CLIENTI interessati", cur.fetchall(), "id | nome")
        cur.execute("""
            SELECT o.public_id, o.version, o.stato::text, o.data_consegna_prevista, ro.public_id,
                   ro.version, v.denominazione, ro.quantita, ro.unita_misura::text,
                   COALESCE((SELECT SUM(rc.quantita) FROM tpo.righe_consegna rc
                             JOIN tpo.consegne c ON c.id = rc.consegna_id
                             WHERE rc.riga_ordine_id = ro.id AND c.stato = 'CONSEGNATA'), 0)
            FROM tpo.ordini o JOIN tpo.clienti cl ON cl.id = o.cliente_id
            JOIN tpo.righe_ordine ro ON ro.ordine_id = o.id
            JOIN tpo.varieta v ON v.id = ro.varieta_id
            WHERE cl.denominazione ILIKE '%bahia%' AND o.stato <> 'ANNULLATO'
            ORDER BY o.data_consegna_prevista, o.public_id, ro.posizione""")
        show("ORDINI Bahia", cur.fetchall(),
             "ordine | ver | stato | prevista | riga | ver | varieta | qta | unita | gia' consegnato")
        cur.execute("""SELECT sequence_name, next_value FROM tpo.id_sequences
                       WHERE sequence_name IN ('ORDINE_ID','RIGA_ORDINE_ID','MOVIMENTO_ID','CONSEGNA_ID')
                       ORDER BY sequence_name""")
        show("CONTATORI id_sequences (prossimo valore)", cur.fetchall(), "sequenza | prossimo")
        cur.execute("""SELECT 'ORDINE', max(substring(public_id from 5)::int) FROM tpo.ordini
                       UNION ALL SELECT 'RIGA_ORDINE', max(substring(public_id from 4)::int) FROM tpo.righe_ordine
                       UNION ALL SELECT 'MOVIMENTO', max(substring(public_id from 5)::int) FROM tpo.movimenti_magazzino
                       UNION ALL SELECT 'CONSEGNA', max(substring(public_id from 5)::int) FROM tpo.consegne""")
        show("MASSIMO reale gia' usato (il contatore deve essere maggiore)", cur.fetchall(), "tipo | massimo")
finally:
    conn.close()
