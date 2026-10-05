"""Diagnostica di SOLA LETTURA degli ordini ancora aperti (5/10/2026).
Serve a decidere come chiudere gli ordini vecchi SENZA inventare consegne: per ogni ordine
APERTO / PARZIALMENTE_EVASO mostra tipo, programma, cliente, date, righe, quantita' consegnata,
cosa lo referenzia (piani, allocazioni, fatture, consegne) e lo stato dei programmi di fornitura.
Non scrive nulla.

Uso: .venv/bin/python scripts/commissioning/2026-10-05_diagnostica_ordini_aperti.py
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


def show(title, header, sql, params=None):
    print(f"\n== {title}")
    print(header)
    cur.execute(sql, params)
    rows = cur.fetchall()
    for r in rows:
        print(" | ".join("-" if x is None else str(x) for x in r))
    if not rows:
        print("(nessuna riga)")


show("RIEPILOGO ORDINI PER STATO / TIPO", "stato | tipo | n. ordini | prima consegna prevista | ultima",
     """SELECT stato::text, tipo_creazione::text, count(*), min(data_consegna_prevista), max(data_consegna_prevista)
        FROM tpo.ordini GROUP BY 1,2 ORDER BY 1,2""")

show("ORDINI APERTI PER MESE DI CONSEGNA PREVISTA", "mese | tipo | n. ordini | con consegne registrate",
     """SELECT to_char(o.data_consegna_prevista,'YYYY-MM'), o.tipo_creazione::text, count(*),
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM tpo.righe_ordine ro
                   JOIN tpo.righe_consegna rc ON rc.riga_ordine_id=ro.id WHERE ro.ordine_id=o.id))
        FROM tpo.ordini o WHERE o.stato IN ('APERTO','PARZIALMENTE_EVASO') GROUP BY 1,2 ORDER BY 1,2""")

show("ORDINI APERTI / PARZIALI (dettaglio)",
     "ordine | stato | tipo | cliente | ordinato il | consegna prevista | programma (stato) | righe: varieta qta [consegnata] | consegne CONSEGNATE",
     """SELECT o.public_id, o.stato::text, o.tipo_creazione::text, cl.denominazione, o.data_ordine,
               o.data_consegna_prevista, pf.public_id||' ('||COALESCE(pv.stato::text,'?')||')',
               (SELECT string_agg(v.denominazione||' '||ro.quantita||' '||ro.unita_misura::text||
                       ' ['||COALESCE((SELECT SUM(rc.quantita) FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id
                              WHERE rc.riga_ordine_id=ro.id AND c.stato='CONSEGNATA'),0)||']', '; ' ORDER BY ro.posizione)
                  FROM tpo.righe_ordine ro JOIN tpo.varieta v ON v.id=ro.varieta_id WHERE ro.ordine_id=o.id),
               (SELECT count(DISTINCT c.id) FROM tpo.righe_ordine ro JOIN tpo.righe_consegna rc ON rc.riga_ordine_id=ro.id
                   JOIN tpo.consegne c ON c.id=rc.consegna_id WHERE ro.ordine_id=o.id AND c.stato='CONSEGNATA')
        FROM tpo.ordini o JOIN tpo.clienti cl ON cl.id=o.cliente_id
        LEFT JOIN tpo.programmi_fornitura pf ON pf.id=o.programma_fornitura_id
        LEFT JOIN LATERAL (SELECT stato FROM tpo.programmi_fornitura_versioni v WHERE v.programma_fornitura_id=pf.id
                           ORDER BY numero_versione DESC LIMIT 1) pv ON true
        WHERE o.stato IN ('APERTO','PARZIALMENTE_EVASO') ORDER BY o.data_consegna_prevista, o.public_id""")

show("PROGRAMMI DI FORNITURA", "programma | stato | cliente | ordini aperti | ordini totali",
     """SELECT pf.public_id, (SELECT stato::text FROM tpo.programmi_fornitura_versioni v
                                   WHERE v.programma_fornitura_id=pf.id ORDER BY numero_versione DESC LIMIT 1),
               cl.denominazione,
               count(o.id) FILTER (WHERE o.stato IN ('APERTO','PARZIALMENTE_EVASO')), count(o.id)
        FROM tpo.programmi_fornitura pf JOIN tpo.clienti cl ON cl.id=pf.cliente_id
        LEFT JOIN tpo.ordini o ON o.programma_fornitura_id=pf.id GROUP BY pf.id,pf.public_id,cl.denominazione ORDER BY 1""")

show("CHI REFERENZIA ORDINI / RIGHE D'ORDINE (tabelle con chiave esterna)", "tabella.colonna | -> | righe che puntano a ordini APERTI/PARZIALI",
     """SELECT conrelid::regclass::text||'.'||a.attname, confrelid::regclass::text, 0
        FROM pg_constraint k JOIN pg_attribute a ON a.attrelid=k.conrelid AND a.attnum=k.conkey[1]
        WHERE k.contype='f' AND k.confrelid IN ('tpo.ordini'::regclass,'tpo.righe_ordine'::regclass)
        ORDER BY 1""")

for table, col, kind in (("righe_piano_semina", "riga_ordine_id", "righe"),):
    show("RIGHE DI PIANO SU ORDINI APERTI", "revisione corrente? | n. righe piano | n. ordini",
         """SELECT CASE WHEN EXISTS (SELECT 1 FROM tpo.piani_produzione pp WHERE pp.current_revision_id=l.piano_revisione_id)
                       THEN 'corrente' ELSE 'storica' END, count(*), count(DISTINCT ro.ordine_id)
            FROM tpo.righe_piano_semina l JOIN tpo.righe_ordine ro ON ro.id=l.riga_ordine_id
            JOIN tpo.ordini o ON o.id=ro.ordine_id WHERE o.stato IN ('APERTO','PARZIALMENTE_EVASO') GROUP BY 1""")

show("ALLOCAZIONI ATTIVE SU ORDINI APERTI", "tipo | n. allocazioni | quantita'",
     """SELECT a.allocation_type, count(*), sum(a.quantity) FROM tpo.allocazioni a
        JOIN tpo.righe_piano_semina l ON l.id=a.riga_piano_semina_id
        JOIN tpo.righe_ordine ro ON ro.id=l.riga_ordine_id JOIN tpo.ordini o ON o.id=ro.ordine_id
        WHERE a.state='ATTIVA' AND o.stato IN ('APERTO','PARZIALMENTE_EVASO') GROUP BY 1 ORDER BY 1""")

show("SEMINE NON CHIUSE", "stato | n. semine | seme totale | varieta'",
     """SELECT s.stato::text, count(*), sum(s.quantita_seme)::text||' g', string_agg(DISTINCT v.denominazione, ', ')
        FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id WHERE s.stato<>'CHIUSA' GROUP BY 1 ORDER BY 1""")

show("STOCK ATTUALE", "varieta | unita | disponibile",
     """SELECT v.denominazione, s.unita_misura::text, s.disponibile FROM tpo.stock s JOIN tpo.varieta v ON v.id=s.varieta_id
        ORDER BY 1,2""")
conn.close()
