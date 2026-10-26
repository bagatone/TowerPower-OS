"""SOLA LETTURA - REPORT VENDITE (23/10/2026): tutte le consegne effettuate, per cliente, per settimana e per varieta'.

  .venv/bin/python scripts/commissioning/2026-10-23_report_vendite.py
  .venv/bin/python scripts/commissioning/2026-10-23_report_vendite.py --csv outputs/report_vendite.csv
  ... --dal 2026-10-01 --al 2026-10-22        (solo un periodo, estremi inclusi; giorni nel fuso delle Canarie)

Cosa mostra: consegne, SET e valore al LISTINO (prezzo unitario x quantita', IGIC non aggiunta: Tower Power e' esente),
totale per cliente, per settimana (lunedi'-domenica) e per varieta', e quanto e' gia' incassato (consegne con un
pagamento valido) e quanto resta da incassare.

ATTENZIONE, due limiti dichiarati nel report:
  - il VALORE e' calcolato col listino di OGGI per tutte le consegne (il sistema non ha registrato i prezzi del
    passato): e' il valore "a 12,50 EUR a SET", non una fattura emessa;
  - sono vendite REGISTRATE a sistema: restano fuori i campioni/prove non registrati (es. Pak Choi di prova).
Una riga in unita' diversa da SET (es. GRAM) non ha valore calcolato (viene contata a parte). Non scrive nulla.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

TIMEZONE = ZoneInfo("Atlantic/Canary")
CENT = Decimal("0.01")

SQL = """
SELECT c.public_id, c.data_effettiva, cl.public_id, cl.denominazione, v.denominazione, rc.quantita,
       rc.unita_misura::text, rc.rettifica_riga_consegna_id IS NOT NULL, l.prezzo_unitario,
       p.public_id, p.data_pagamento, p.metodo::text, p.importo
FROM tpo.consegne c
JOIN tpo.clienti cl ON cl.id = c.cliente_id
JOIN tpo.righe_consegna rc ON rc.consegna_id = c.id
JOIN tpo.varieta v ON v.id = rc.varieta_id
LEFT JOIN tpo.listino_varieta l ON l.varieta_id = rc.varieta_id
LEFT JOIN tpo.pagamenti_consegna p ON p.consegna_id = c.id AND p.tipo = 'PAGAMENTO'
     AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna a WHERE a.annulla_pagamento_id = p.id)
WHERE c.stato = 'CONSEGNATA'
ORDER BY c.data_effettiva, c.public_id, rc.posizione"""


def _n(value) -> str:
    text = format(Decimal(value).normalize(), "f")
    return text if "." not in text else text.rstrip("0").rstrip(".")


def _euro(value: Decimal) -> str:
    return f"{value.quantize(CENT, rounding=ROUND_HALF_UP):.2f} EUR"


def _lunedi(giorno: date) -> date:
    return giorno - timedelta(days=giorno.weekday())


def raccogli(conn, dal: date | None = None, al: date | None = None) -> list[dict]:
    """Una voce per riga di consegna, con data locale, valore al listino e stato di pagamento."""
    conn.read_only = True
    cur = conn.cursor()
    cur.execute(SQL)
    voci = []
    for (cons, effettiva, cli_pid, cliente, varieta, qty, uom, rettifica, prezzo,
         pag_id, pag_data, pag_metodo, pag_importo) in cur.fetchall():
        giorno = effettiva.astimezone(TIMEZONE).date()
        if (dal and giorno < dal) or (al and giorno > al):
            continue
        qty = Decimal(qty)
        valore = None if (prezzo is None or uom != "SET") else qty * Decimal(prezzo)
        voci.append({
            "consegna": cons, "data": giorno, "cliente_id": cli_pid, "cliente": cliente, "varieta": varieta,
            "quantita": qty, "unita": uom, "rettifica": bool(rettifica),
            "prezzo": None if prezzo is None else Decimal(prezzo), "valore": valore,
            "pagata": pag_id is not None, "pagamento": pag_id, "data_pagamento": pag_data, "metodo": pag_metodo,
            "importo_pagato": None if pag_importo is None else Decimal(pag_importo),
        })
    conn.rollback()
    return voci


def _riepilogo(voci, chiave):
    """{chiave: {consegne:set, set:Decimal, valore:Decimal, incassato:Decimal, da_incassare:Decimal}}"""
    tab: dict = defaultdict(lambda: {"consegne": set(), "set": Decimal(0), "valore": Decimal(0),
                                     "incassato": Decimal(0), "da_incassare": Decimal(0)})
    for v in voci:
        r = tab[chiave(v)]
        r["consegne"].add(v["consegna"])
        if v["unita"] == "SET":
            r["set"] += v["quantita"]
        if v["valore"] is not None:
            r["valore"] += v["valore"]
            r["incassato" if v["pagata"] else "da_incassare"] += v["valore"]
    return tab


def _tabella(titolo, tab, out, ordine=None, etichetta=lambda k: str(k)):
    out(f"\n-- {titolo}")
    out(f"   {'':32} {'consegne':>8} {'SET':>7} {'valore':>12} {'incassato':>12} {'da incassare':>13}")
    for k in sorted(tab, key=ordine):
        r = tab[k]
        out(f"   {etichetta(k):32} {len(r['consegne']):>8} {_n(r['set']):>7} {_euro(r['valore']):>12} "
            f"{_euro(r['incassato']):>12} {_euro(r['da_incassare']):>13}")


def run(conn, dal: date | None = None, al: date | None = None, csv_path: str | None = None, out=print) -> int:
    voci = raccogli(conn, dal, al)
    periodo = (f" dal {dal.isoformat() if dal else 'inizio'} al {al.isoformat() if al else 'oggi'}"
               if (dal or al) else "")
    out(f"== REPORT VENDITE{periodo} (SOLA LETTURA, NULLA SCRITTO)")
    if not voci:
        out("Nessuna consegna effettuata nel periodo.")
        return 0
    prima, ultima = min(v["data"] for v in voci), max(v["data"] for v in voci)
    consegne = {v["consegna"] for v in voci}
    tot = _riepilogo(voci, lambda v: "TOTALE")["TOTALE"]
    out(f"Periodo coperto dalle consegne: {prima.isoformat()} -> {ultima.isoformat()} ({(ultima - prima).days + 1} giorni)")
    out(f"Consegne: {len(consegne)}   Clienti: {len({v['cliente_id'] for v in voci})}   SET: {_n(tot['set'])}")
    out(f"Valore al listino: {_euro(tot['valore'])}  (incassato {_euro(tot['incassato'])}, "
        f"da incassare {_euro(tot['da_incassare'])})")
    _tabella("PER CLIENTE", _riepilogo(voci, lambda v: v["cliente"]), out,
             ordine=lambda k: -_riepilogo(voci, lambda v: v["cliente"])[k]["valore"])
    _tabella("PER SETTIMANA (lunedi')", _riepilogo(voci, lambda v: _lunedi(v["data"])), out,
             etichetta=lambda k: f"settimana dal {k.strftime('%d/%m/%Y')}")
    _tabella("PER VARIETA'", _riepilogo(voci, lambda v: v["varieta"]), out,
             ordine=lambda k: -_riepilogo(voci, lambda v: v["varieta"])[k]["set"])
    senza = sorted({v["varieta"] for v in voci if v["prezzo"] is None and v["unita"] == "SET"})
    non_set = [v for v in voci if v["unita"] != "SET"]
    rettifiche = [v for v in voci if v["rettifica"]]
    out("\n-- NOTE")
    out("   Valore = quantita' x prezzo di listino di OGGI, uguale per tutte le consegne (i prezzi del passato non erano "
        "registrati): non e' un incasso ne' una fattura.")
    out("   Solo vendite registrate a sistema: restano fuori campioni e prove non registrati.")
    if senza:
        out(f"   Listino senza prezzo, valore NON calcolato per: {', '.join(senza)}.")
    if non_set:
        out(f"   {len(non_set)} righe non in SET (es. grammi): contate a parte, senza valore.")
    if rettifiche:
        out(f"   {len(rettifiche)} righe sono rettifiche di consegne: il valore e' indicativo.")
    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as handle:
            w = csv.writer(handle, delimiter=";")
            w.writerow(["consegna", "data", "codice_cliente", "cliente", "varieta", "quantita", "unita", "rettifica",
                        "prezzo_listino", "valore", "pagata", "pagamento", "data_pagamento", "metodo", "importo_pagato"])
            for v in voci:
                w.writerow([v["consegna"], v["data"].isoformat(), v["cliente_id"], v["cliente"], v["varieta"],
                            _n(v["quantita"]), v["unita"], "si" if v["rettifica"] else "no",
                            "" if v["prezzo"] is None else _n(v["prezzo"]),
                            "" if v["valore"] is None else str(v["valore"].quantize(CENT, rounding=ROUND_HALF_UP)),
                            "si" if v["pagata"] else "no", v["pagamento"] or "",
                            v["data_pagamento"].isoformat() if v["data_pagamento"] else "", v["metodo"] or "",
                            "" if v["importo_pagato"] is None else _n(v["importo_pagato"])])
        out(f"\nCSV scritto: {csv_path}")
    return 0


def _data(text: str) -> date:
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit(f"STOP: data non valida {text!r} (usa AAAA-MM-GG).")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dal", help="AAAA-MM-GG, incluso")
    ap.add_argument("--al", help="AAAA-MM-GG, incluso")
    ap.add_argument("--csv", metavar="FILE", help="scrive anche un CSV (una riga per riga di consegna)")
    a = ap.parse_args()
    dal, al = (_data(a.dal) if a.dal else None), (_data(a.al) if a.al else None)
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, dal, al, a.csv)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
