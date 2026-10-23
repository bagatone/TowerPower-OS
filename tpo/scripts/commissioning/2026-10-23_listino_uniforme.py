"""LISTINO UNIFORME (23/10/2026, richiesta di Matteo): stesso prezzo a SET per TUTTE le varieta', per il momento.

  .venv/bin/python scripts/commissioning/2026-10-23_listino_uniforme.py                 # anteprima (12,50 EUR, IGIC 0)
  .venv/bin/python scripts/commissioning/2026-10-23_listino_uniforme.py --esegui        # scrive davvero
  ... --prezzo 12.50 --igic 0                                                          # valori (default quelli di sopra)
  ... --anche-dismesse                                                                 # include le varieta' DISMESSE

Matteo (23/10/2026): 12,50 EUR a SET e' il prezzo FINALE, "siamo esenti da IGIC": aliquota IGIC 0, prezzo = netto = totale.
Il listino ha UN prezzo per varieta' (non per cliente): vale per tutti i clienti e per tutte le bolle/fatture generate DOPO.
Attenzione: le bolle si ricalcolano dal listino AL MOMENTO della generazione; se cambi il prezzo, una bolla rigenerata
dopo mostrera' il prezzo nuovo.

Cosa fa con --esegui: per ogni varieta' ATTIVA chiama il comando governato `tpo listino-varieta set` (upsert; evento di
audit LISTINO_VARIETA con prezzo prima/dopo e motivo). Rilanciarlo con gli stessi valori non cambia nulla (stessi
valori, stessa chiave di correlazione). Non tocca ordini, consegne, fatture gia' emesse.

COMANDO CORRETTIVO: per ogni varieta' che aveva gia' un prezzo viene stampato il comando che lo rimette com'era;
una varieta' senza prezzo non puo' tornare "senza listino" (non esiste cancellazione): si cambia il prezzo.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
ACTOR = "matteo"
TAG = "listino-uniforme-2026-10-23"
MOTIVO = "Listino uniforme dichiarato da Matteo il 23/10/2026: stesso prezzo a SET per tutte le varieta'"

SQL = """SELECT v.public_id, v.denominazione, v.stato::text, l.prezzo_unitario, l.aliquota_igic
FROM tpo.varieta v LEFT JOIN tpo.listino_varieta l ON l.varieta_id = v.id
ORDER BY v.public_id"""


def _dec(text: str, nome: str) -> Decimal:
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        raise SystemExit(f"STOP: {nome} non e' un numero: {text!r}")


def _fmt(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f").replace(".", ",")


def _comando(varieta: str, prezzo: Decimal, igic: Decimal, motivo: str, correlazione: str) -> list[str]:
    return ["listino-varieta", "set", "--varieta", varieta, "--prezzo-unitario", format(prezzo, "f"),
            "--aliquota-igic", format(igic, "f"), "--actor", ACTOR, "--reason", motivo,
            "--correlation-id", correlazione]


def _mostra(argv: list[str]) -> str:
    return "tpo " + " ".join(a if re.fullmatch(r"[\w./:+=,@-]+", a) else repr(a) for a in argv)


def run(conn, prezzo: Decimal, igic: Decimal, esegui: bool, anche_dismesse: bool = False,
        esegui_tpo=None, out=print) -> int:
    """Legge le varieta' e (con esegui) imposta il listino con `esegui_tpo(argv) -> (codice, testo)`."""
    if prezzo < 0 or igic < 0 or igic > 100:
        out("STOP: prezzo negativo o IGIC fuori da 0-100.")
        return 2
    conn.read_only = True
    cur = conn.cursor()
    cur.execute(SQL)
    varieta = cur.fetchall()
    conn.rollback()
    scelte = [v for v in varieta if anche_dismesse or v[2] == "ATTIVA"]
    saltate = [v for v in varieta if v not in scelte]
    out(f"== LISTINO UNIFORME -- {'ESECUZIONE' if esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    out(f"Prezzo a SET: {_fmt(prezzo)} EUR, IGIC {igic}% (prezzo finale: nessuna imposta aggiunta se IGIC 0)\n")
    da_fare, correttivi = [], []
    for pid, nome, stato, p_prima, ig_prima in scelte:
        if p_prima is None:
            stato_txt = "nessun prezzo -> nuovo"
        elif Decimal(p_prima) == prezzo and Decimal(ig_prima) == igic:
            stato_txt = "gia' cosi', nulla da cambiare"
        else:
            stato_txt = f"era {_fmt(Decimal(p_prima))} EUR IGIC {Decimal(ig_prima)}% -> cambia"
            correttivi.append((pid, Decimal(p_prima), Decimal(ig_prima)))
        out(f"  {pid} | {nome} | {stato_txt}")
        if "gia' cosi'" not in stato_txt:
            da_fare.append((pid, nome))
    for pid, nome, stato, *_ in saltate:
        out(f"  {pid} | {nome} | {stato}: saltata (usa --anche-dismesse per includerla)")
    if not da_fare:
        out("\nNulla da scrivere: il listino e' gia' a questi valori.")
        return 0
    if not esegui:
        out(f"\nANTEPRIMA: nulla e' stato scritto ({len(da_fare)} varieta' da impostare). Per eseguire aggiungi --esegui")
        return 0
    fatte = []
    for pid, nome in da_fare:
        argv = _comando(pid, prezzo, igic, MOTIVO, f"{TAG}-{pid}")
        codice, testo = esegui_tpo(argv)
        if codice != 0:
            out(f"\nSTOP: {pid} {nome} fallita (exit {codice}): {testo.strip()}")
            out(f"Impostate prima dell'errore: {', '.join(fatte) or 'nessuna'}. Rilancia: le gia' fatte non cambiano.")
            return 1
        fatte.append(pid)
        out(f"  FATTO {pid} {nome}: {_fmt(prezzo)} EUR")
    out(f"\nFATTO: listino impostato su {len(fatte)} varieta' a {_fmt(prezzo)} EUR (IGIC {igic}%).")
    out("\n== COMANDI CORRETTIVI")
    if correttivi:
        for pid, p_prima, ig_prima in correttivi:
            argv = _comando(pid, p_prima, ig_prima, "Ripristinato il prezzo precedente (correzione richiesta da Matteo)",
                            f"{TAG}-ripristino-{pid}")
            out("   " + _mostra(argv))
    else:
        out("   nessuna varieta' aveva un prezzo prima: per cambiare un prezzo rilancia questo script con --prezzo.")
    return 0


def _esegui_tpo(argv):
    done = subprocess.run([RUN, *argv], capture_output=True, text=True)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prezzo", default="12.50", help="EUR per SET (default 12.50)")
    ap.add_argument("--igic", default="0", help="aliquota IGIC percentuale (default 0)")
    ap.add_argument("--anche-dismesse", action="store_true")
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, _dec(a.prezzo, "--prezzo"), _dec(a.igic, "--igic"), a.esegui, a.anche_dismesse, _esegui_tpo)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
