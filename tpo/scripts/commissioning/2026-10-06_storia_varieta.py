"""SOLA LETTURA - storia completa di una o piu' varieta': semine (anche chiuse), raccolte, carichi e scarichi di magazzino, stock.

Serve a far tornare i conti quando il conteggio fisico non coincide con il sistema. Non scrive nulla.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-06_storia_varieta.py Hinojo Amaranto
"""
from __future__ import annotations

import sys
import unicodedata
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))


def _n(value) -> str:
    return "-" if value is None else format(Decimal(value).normalize(), "f")


def _norm(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)).strip()


def run(conn, wanted, out=print) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id, denominazione FROM tpo.varieta ORDER BY denominazione")
    varieties = {_norm(name): (vid, name) for vid, name in cur.fetchall()}
    unknown = [w for w in wanted if _norm(w) not in varieties]
    if unknown:
        out(f"STOP: varieta' sconosciute: {', '.join(unknown)}; esistenti: {', '.join(v[1] for v in varieties.values())}")
        return 2
    for item in wanted:
        vid, name = varieties[_norm(item)]
        out(f"\n==================== {name} (NULLA E' STATO SCRITTO)")
        cur.execute("""SELECT s.public_id, s.stato::text, s.data_avvio, s.quantita_seme, s.expected_useful_quantity,
                              s.harvest_window_start,
                              COALESCE((SELECT SUM(rc.quantita) FROM tpo.raccolte rc
                                        WHERE rc.semina_id=s.id AND rc.unita_misura='SET'),0)
                       FROM tpo.semine s WHERE s.varieta_id=%s ORDER BY s.data_avvio, s.public_id""", (vid,))
        out("-- Semine (tutte, anche chiuse): semina | stato | avviata | seme g | SET attesi | SET raccolti | pronta dal")
        for pid, stato, avvio, grams, exp, w0, harvested in cur.fetchall():
            out(f"{pid} | {stato} | {avvio:%Y-%m-%d} | {_n(grams)} | {_n(exp)} | {_n(harvested)} | "
                f"{w0:%Y-%m-%d}" if w0 else f"{pid} | {stato} | {avvio:%Y-%m-%d} | {_n(grams)} | {_n(exp)} | {_n(harvested)} | -")
        cur.execute("""SELECT rc.public_id, s.public_id, rc.data_raccolta, rc.quantita, rc.unita_misura::text
                       FROM tpo.raccolte rc JOIN tpo.semine s ON s.id=rc.semina_id
                       WHERE s.varieta_id=%s ORDER BY rc.data_raccolta, rc.id""", (vid,))
        out("-- Raccolte: raccolta | semina | data | quantita")
        for pid, sid, when, qty, uom in cur.fetchall():
            out(f"{pid} | {sid} | {when:%Y-%m-%d %H:%M} | {_n(qty)} {uom}")
        cur.execute("""SELECT public_id, data_movimento, tipo::text, direzione::text, quantita, unita_misura::text, motivo
                       FROM tpo.movimenti_magazzino WHERE varieta_id=%s ORDER BY data_movimento, id""", (vid,))
        out("-- Movimenti di magazzino: movimento | data | tipo | direzione | quantita | motivo")
        for pid, when, tipo, direzione, qty, uom, motivo in cur.fetchall():
            out(f"{pid} | {when:%Y-%m-%d %H:%M} | {tipo} | {direzione} | {_n(qty)} {uom} | {motivo}")
        cur.execute("SELECT unita_misura::text, disponibile FROM tpo.stock WHERE varieta_id=%s", (vid,))
        out("-- Stock disponibile: " + (", ".join(f"{_n(q)} {u}" for u, q in cur.fetchall()) or "nessuno"))
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
