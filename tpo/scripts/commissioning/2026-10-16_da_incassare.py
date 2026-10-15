"""SOLA LETTURA - elenco "DA INCASSARE": le consegne effettuate e non ancora pagate, per cliente (16/10/2026).

Per ogni cliente: le consegne da pagare (la piu' vecchia per prima) con data, giorni trascorsi, voci consegnate e
valore da LISTINO (netto, IGIC esclusa: quantita' x prezzo_unitario, come lo calcola l'emissione fattura). Se per una
varieta' il listino non ha il prezzo, il valore di quella consegna NON viene calcolato e lo dice. Se il cliente ha i
termini di pagamento (giorni) mostra la scadenza e marca SCADUTA quella passata.

Stampa, per ogni cliente, il comando pronto per registrare il pagamento di TUTTE le sue consegne in una volta
(2026-10-11_pagamenti_consegne.py --pagata CON-... CON-... --metodo M --esegui). Per pagare solo alcune consegne togli
i codici che non servono. Con --metodo il comando esce gia' completo; senza, trovi METODO da sostituire.

Non scrive nulla. Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-16_da_incassare.py                  # tutti i clienti
  .venv/bin/python scripts/commissioning/2026-10-16_da_incassare.py --cliente Bahia  # un cliente (anche parte del nome)
  .venv/bin/python scripts/commissioning/2026-10-16_da_incassare.py --metodo CONTANTI
Opzione: --csv FILE  scrive anche un CSV apribile con Excel/Numbers.
"""
from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

TIMEZONE = ZoneInfo("Atlantic/Canary")
METODI = ("BONIFICO", "CONTANTI", "CARTA", "BIZUM", "ALTRO")
PAGAMENTI = "scripts/commissioning/2026-10-11_pagamenti_consegne.py"
CENT = Decimal("0.01")

SQL_CONSEGNE = """
SELECT c.id, c.public_id, cl.public_id, cl.denominazione, c.data_effettiva, cl.termini_pagamento_giorni
FROM tpo.consegne c JOIN tpo.clienti cl ON cl.id=c.cliente_id
WHERE c.stato='CONSEGNATA'
  AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna p
                  WHERE p.consegna_id=c.id AND p.tipo='PAGAMENTO'
                    AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna a WHERE a.annulla_pagamento_id=p.id))
ORDER BY c.data_effettiva, c.public_id"""
SQL_RIGHE = """
SELECT rc.consegna_id, v.denominazione, rc.quantita, rc.unita_misura::text, rc.rettifica_riga_consegna_id IS NOT NULL,
       l.prezzo_unitario
FROM tpo.righe_consegna rc JOIN tpo.varieta v ON v.id=rc.varieta_id
LEFT JOIN tpo.listino_varieta l ON l.varieta_id=rc.varieta_id
WHERE rc.consegna_id = ANY(%s) ORDER BY rc.consegna_id, rc.posizione"""


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def _euro(value: Decimal) -> str:
    return f"{value.quantize(CENT, rounding=ROUND_HALF_UP):.2f} EUR"


def raccogli(conn, cliente: str | None = None, oggi: date | None = None):
    """[(cliente_public_id, nome, [consegna dict ordinate dalla piu' vecchia])] per i clienti con consegne da pagare."""
    oggi = oggi or datetime.now(TIMEZONE).date()
    cur = conn.cursor()
    cur.execute(SQL_CONSEGNE)
    consegne = cur.fetchall()
    if cliente:
        consegne = [r for r in consegne if _fold(cliente) in _fold(r[3])]
    righe: dict[int, list] = defaultdict(list)
    if consegne:
        cur.execute(SQL_RIGHE, ([r[0] for r in consegne],))
        for cons_pk, nome, qty, uom, rettifica, prezzo in cur.fetchall():
            righe[cons_pk].append((nome, Decimal(qty), uom, rettifica, None if prezzo is None else Decimal(prezzo)))
    per_cliente: dict[str, list] = {}
    nomi: dict[str, str] = {}
    for pk, pid, cli_pid, nome_cli, effettiva, termini in consegne:
        giorno = effettiva.astimezone(TIMEZONE).date()
        voci = righe.get(pk, [])
        mancanti = sorted({v[0] for v in voci if v[4] is None})
        valore = None if (not voci or mancanti) else sum((v[1] * v[4] for v in voci), Decimal(0))
        per_cliente.setdefault(cli_pid, []).append({
            "consegna": pid, "data": giorno, "giorni": (oggi - giorno).days, "voci": voci, "valore": valore,
            "listino_mancante": mancanti, "rettifiche": any(v[3] for v in voci),
            "scadenza": giorno + timedelta(days=int(termini)) if termini else None,
        })
        nomi[cli_pid] = nome_cli
    elenco = [(cli, nomi[cli], sorted(c, key=lambda x: (x["data"], x["consegna"]))) for cli, c in per_cliente.items()]
    return sorted(elenco, key=lambda e: (e[2][0]["data"], e[1]))        # prima il cliente con la consegna piu' vecchia


def run(conn, cliente: str | None = None, metodo: str | None = None, csv_path: str | None = None,
        oggi: date | None = None, out=print) -> int:
    oggi = oggi or datetime.now(TIMEZONE).date()
    if metodo and metodo.upper() not in METODI:
        out(f"STOP: metodo '{metodo}' non valido ({'|'.join(METODI)}).")
        return 2
    elenco = raccogli(conn, cliente, oggi)
    out(f"== DA INCASSARE al {oggi.isoformat()} (SOLA LETTURA, NULLA SCRITTO)"
        + (f" - cliente '{cliente}'" if cliente else ""))
    if not elenco:
        out("Nessuna consegna da incassare" + (f" per '{cliente}'." if cliente else ": tutte le consegne sono pagate."))
        return 0
    tot_consegne = tot_valore = 0
    senza_valore = 0
    senza_prezzo: set[str] = set()
    righe_csv = []
    for cli_pid, nome, consegne in elenco:
        valore_cli = sum((c["valore"] for c in consegne if c["valore"] is not None), Decimal(0))
        incompleto = any(c["valore"] is None for c in consegne)
        out(f"\n{nome} ({cli_pid}): {len(consegne)} consegn{'a' if len(consegne) == 1 else 'e'}, "
            f"la piu' vecchia di {consegne[0]['giorni']} giorn{'o' if consegne[0]['giorni'] == 1 else 'i'}"
            + (f" - da listino {_euro(valore_cli)}{' (+ consegne senza valore)' if incompleto else ''}"
               if valore_cli or not incompleto else ""))
        for c in consegne:
            voci = ", ".join(f"{n} {_n(q)}" for n, q, *_ in c["voci"]) or "(nessuna riga)"
            if c["valore"] is not None:
                val = _euro(c["valore"]) + (" (ha rettifiche: indicativo)" if c["rettifiche"] else "")
            else:
                val = "valore n.d."
                senza_prezzo.update(c["listino_mancante"])
            scad = ""
            if c["scadenza"]:
                scad = f"  scad. {c['scadenza'].isoformat()}" + (" SCADUTA" if c["scadenza"] < oggi else "")
            out(f"   {c['consegna']}  {c['data'].isoformat()} ({c['giorni']} gg)  {voci}  -> {val}{scad}")
            righe_csv.append([nome, cli_pid, c["consegna"], c["data"].isoformat(), c["giorni"], voci,
                              "" if c["valore"] is None else str(c["valore"].quantize(CENT, rounding=ROUND_HALF_UP)),
                              c["scadenza"].isoformat() if c["scadenza"] else ""])
            tot_consegne += 1
            if c["valore"] is None:
                senza_valore += 1
            else:
                tot_valore += c["valore"]
        codici = " ".join(c["consegna"] for c in consegne)
        out(f"   Pagate tutte:  .venv/bin/python {PAGAMENTI} --pagata {codici} --metodo {metodo.upper() if metodo else 'METODO'}"
            + (" --esegui" if metodo else "  (metodi: " + "|".join(METODI) + "; aggiungi --esegui)"))
    if tot_consegne == senza_valore:
        valore_txt = "valore da listino non calcolabile"
    else:
        valore_txt = f"da listino {_euro(Decimal(tot_valore))} netto (IGIC esclusa)" + \
            (f"; {senza_valore} consegne senza valore calcolabile" if senza_valore else "")
    out(f"\nTOTALE: {tot_consegne} consegne da incassare, {len(elenco)} clienti, {valore_txt}")
    if senza_prezzo:
        out("NOTA: il listino non ha il prezzo di: " + ", ".join(sorted(senza_prezzo)) + ". Senza prezzo i valori non si "
            "calcolano (e non si possono emettere fatture). Si imposta con `tpo listino-varieta set` (prezzo e IGIC "
            "sono decisioni tue: non li invento).")
    out("Per cambiare data del pagamento aggiungi --data AAAA-MM-GG (altrimenti: oggi).")
    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["cliente", "codice_cliente", "consegna", "data", "giorni", "voci", "valore_netto_listino",
                             "scadenza"])
            writer.writerows(righe_csv)
        out(f"CSV scritto: {csv_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cliente", help="filtra per nome cliente (anche una parte)")
    ap.add_argument("--metodo", help="|".join(METODI) + ": completa i comandi di pagamento stampati")
    ap.add_argument("--csv", metavar="FILE", help="scrive anche un CSV")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"], autocommit=True)
    try:
        return run(conn, a.cliente, a.metodo, a.csv)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
