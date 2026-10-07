"""SOLA LETTURA - righe d'ordine aperte di una o piu' varieta', con cliente, date, quantita' e origine dell'ordine.

Serve a capire DA CHI viene la domanda (es. le righe grosse di Cilantro). Non scrive nulla.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-07_ordini_varieta.py Cilantro
  .venv/bin/python scripts/commissioning/2026-10-07_ordini_varieta.py Cilantro Rabano
"""
from __future__ import annotations

import sys
import unicodedata
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

SQL = """
SELECT o.public_id, ro.public_id, cl.denominazione, o.data_ordine, o.data_consegna_prevista, o.stato::text,
       o.tipo_creazione::text, pf.public_id, ro.quantita,
       COALESCE((SELECT SUM(rc.quantita) FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id
                 WHERE rc.riga_ordine_id=ro.id AND c.stato='CONSEGNATA'),0)
FROM tpo.righe_ordine ro JOIN tpo.ordini o ON o.id=ro.ordine_id JOIN tpo.clienti cl ON cl.id=o.cliente_id
LEFT JOIN tpo.programmi_fornitura pf ON pf.id=o.programma_fornitura_id
WHERE ro.varieta_id=%s AND o.stato IN ('APERTO','PARZIALMENTE_EVASO') AND ro.unita_misura='SET'
ORDER BY o.data_consegna_prevista, o.public_id, ro.public_id"""


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def _norm(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)).strip()


def run(conn, wanted, out=print) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id, denominazione FROM tpo.varieta")
    varieties = {_norm(name): (vid, name) for vid, name in cur.fetchall()}
    unknown = [w for w in wanted if _norm(w) not in varieties]
    if unknown:
        out(f"STOP: varieta' sconosciute: {', '.join(unknown)}")
        return 2
    for item in wanted:
        vid, name = varieties[_norm(item)]
        cur.execute(SQL, (vid,))
        rows = cur.fetchall()
        out(f"\n== {name}: righe aperte (NULLA E' STATO SCRITTO)")
        out("consegna | ordine | riga | cliente | ordinato il | SET ordinati | consegnati | residuo | stato | origine")
        total = Decimal(0)
        for order, line, client, ordered_on, delivery, state, kind, program, qty, delivered in rows:
            residual = Decimal(qty) - Decimal(delivered)
            total += residual
            origin = kind + (f" ({program})" if program else "")
            out(f"{delivery} | {order} | {line} | {client} | {ordered_on} | {_n(qty)} | {_n(delivered)} | "
                f"{_n(residual)} | {state} | {origin}")
        out(f"TOTALE residuo {name}: {_n(total)} SET")
    return 0


def main() -> int:
    wanted = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not wanted:
        print(__doc__)
        return 2
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"],
                           connect_timeout=p["connect_timeout"], autocommit=True)
    conn.read_only = True
    try:
        return run(conn, wanted)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
