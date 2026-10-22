"""ELENCO CLIENTI (22/10/2026, sola lettura): per ogni cliente nome, id, quanti ordini/consegne/programmi ha e l'ultima
consegna. Serve a vedere a colpo d'occhio se due clienti sono lo stesso ristorante (nomi simili, es. Salvaje/Selvaje) e
quale dei due ha la storia.

  .venv/bin/python scripts/commissioning/2026-10-22_elenco_clienti.py              # tutti
  .venv/bin/python scripts/commissioning/2026-10-22_elenco_clienti.py salvaje      # solo nomi che contengono "salvaje"
                                                                                  # (senza distinzione di maiuscole)
Non scrive nulla: la connessione e' aperta in sola lettura.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

SQL = """SELECT c.public_id, c.denominazione,
       (SELECT count(*) FROM tpo.ordini o WHERE o.cliente_id=c.id),
       (SELECT count(*) FROM tpo.consegne k WHERE k.cliente_id=c.id),
       (SELECT count(*) FROM tpo.programmi_fornitura p WHERE p.cliente_id=c.id),
       (SELECT max(k.data_effettiva) FROM tpo.consegne k WHERE k.cliente_id=c.id)
FROM tpo.clienti c
WHERE (%(q)s = '' OR lower(c.denominazione) LIKE '%%' || lower(%(q)s) || '%%')
ORDER BY lower(c.denominazione), c.public_id"""


def run(conn, cerca: str = "", out=print) -> int:
    conn.read_only = True
    cur = conn.cursor()
    cur.execute(SQL, {"q": cerca.strip()})
    righe = cur.fetchall()
    out(f"== CLIENTI{f' che contengono {cerca!r}' if cerca.strip() else ''}: {len(righe)}")
    for pid, nome, ordini, consegne, programmi, ultima in righe:
        quando = f"{ultima:%d/%m/%Y}" if ultima else "-"
        out(f"  {pid} | {nome} | {ordini} ordini | {consegne} consegne (ultima {quando}) | {programmi} programmi")
    conn.rollback()
    return 0


def main() -> int:
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, " ".join(sys.argv[1:]))
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
