"""SOLA LETTURA - SEMINE IN CORSO per stadio: quanti SET tra germinazione e crescita (16/10/2026, domanda di Matteo).

Non scrive nulla. Legge le semine non CHIUSE e le raggruppa per stadio fisico registrato:
  AVVIATA (idratazione/avvio), GERMINAZIONE, LUCE, CRESCITA, PRONTA_ALLA_RACCOLTA.
Il numero in evidenza e' "tra germinazione e crescita" = GERMINAZIONE + LUCE + CRESCITA (LUCE e CRESCITA sono lo stesso
processo, regola di Matteo). AVVIATA e PRONTA_ALLA_RACCOLTA sono mostrate a parte, non sommate.
I SET sono i SET ATTESI registrati sulla semina (resa attesa in SET); se manca, la semina e' elencata come "SET ?" e non
entra nei totali. Per le PRONTE si vedono anche i SET gia' raccolti.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-16_semine_in_corso.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

STADI = ("AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA")
IN_SEMINA = ("GERMINAZIONE", "LUCE", "CRESCITA")

SQL = """
SELECT s.public_id, s.codice_tracciabilita, v.denominazione, s.stato::text, s.data_avvio,
       s.expected_useful_quantity, s.expected_useful_uom::text,
       COALESCE((SELECT SUM(rc.quantita) FROM tpo.raccolte rc WHERE rc.semina_id=s.id AND rc.unita_misura='SET'),0)
FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
WHERE s.stato<>'CHIUSA' ORDER BY v.denominazione, s.data_avvio, s.public_id"""


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def leggi(cur) -> list[dict]:
    cur.execute(SQL)
    semine = []
    for pid, codice, varieta, stato, avvio, atteso, uom, raccolto in cur.fetchall():
        semine.append({"id": pid, "codice": codice or "senza codice", "varieta": varieta, "stato": stato, "avvio": avvio,
                       "set": Decimal(atteso) if atteso is not None and uom == "SET" else None,
                       "raccolto": Decimal(raccolto)})
    return semine


def totale(semine: list[dict]) -> Decimal:
    return sum((s["set"] for s in semine if s["set"] is not None), Decimal(0))


def rapporto(semine: list[dict]) -> list[str]:
    per_stadio: dict[str, list[dict]] = defaultdict(list)
    for s in semine:
        per_stadio[s["stato"]].append(s)
    in_semina = [s for stadio in IN_SEMINA for s in per_stadio.get(stadio, [])]
    out = ["== SEMINE IN CORSO (SOLA LETTURA, NULLA SCRITTO)", ""]
    out.append(f"TRA GERMINAZIONE E CRESCITA: {_n(totale(in_semina))} SET in {len(in_semina)} semine"
               f" (germinazione {_n(totale(per_stadio.get('GERMINAZIONE', [])))}, "
               f"luce {_n(totale(per_stadio.get('LUCE', [])))}, crescita {_n(totale(per_stadio.get('CRESCITA', [])))})")
    senza = [s for s in in_semina if s["set"] is None]
    if senza:
        out.append("  attenzione: SET ? (resa attesa non compilata, non contata): " + ", ".join(s["id"] for s in senza))
    extra = [("AVVIATA", "AVVIATE (appena messe, non ancora in germinazione)"),
             ("PRONTA_ALLA_RACCOLTA", "PRONTE ALLA RACCOLTA (non sommate sopra)")]
    for stadio, titolo in extra:
        lista = per_stadio.get(stadio, [])
        out.append(f"{titolo}: {_n(totale(lista))} SET in {len(lista)} semine")
    for stadio in STADI:
        lista = per_stadio.get(stadio, [])
        if not lista:
            continue
        out.append(f"\n-- {stadio} ({len(lista)})")
        for s in lista:
            qta = f"{_n(s['set'])} SET" if s["set"] is not None else "SET ?"
            racc = f", raccolti {_n(s['raccolto'])}" if s["raccolto"] > 0 else ""
            out.append(f"   {s['id']} {s['codice']}  {s['varieta']}  {qta}  avviata {s['avvio']:%d/%m}{racc}")
    if not semine:
        out.append("Nessuna semina aperta.")
    return out


def main() -> int:
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"], autocommit=True)
    try:
        for riga in rapporto(leggi(conn.cursor())):
            print(riga)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
