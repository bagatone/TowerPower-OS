"""INVENTARIO di semi, vaschette e substrato - SOLA LETTURA (15/10/2026, richiesta di Matteo).

Non scrive nulla. Mostra quello che il SISTEMA sa:
  1. SEMI: ogni lotto di seme (LSE-...) con fornitore, referenza, lotto del produttore, data di ricezione e di scadenza,
     grammi iniziali e RESIDUI a sistema, anomalia (se registrata) e le varieta' gia' seminate con quel lotto;
     totale residuo per referenza e in complesso;
  2. MATERIALI: ogni articolo di magazzino (ART-...: vaschette, substrato, ...) con giacenza, unita' e data dell'ultimo
     movimento; per vaschette e substrato quanti SET bastano (regola: 4 vaschette + 4 substrati per SET).
  3. SEMINE IN CORSO (16/10/2026, richiesta di Matteo): il TOTALE DEI SET in coltivazione (germinazione + luce + crescita),
     per stadio e per varieta', piu' le semine appena avviate e quelle pronte alla raccolta (a parte); semina per semina nel
     CSV (tipo SEMINA_IN_CORSO) con la riga TOTALE_SET_IN_SEMINA. I SET sono i SET attesi registrati sulla semina.

ATTENZIONE: sono i numeri del sistema, non un conteggio fisico. Il residuo di un lotto scende solo quando una semina
viene registrata con quel lotto; la giacenza degli articoli solo con carichi, consumi per semina e rettifiche.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-15_inventario.py
  .venv/bin/python scripts/commissioning/2026-10-15_inventario.py --csv ~/Desktop/inventario_2026-10-15.csv
  .venv/bin/python scripts/commissioning/2026-10-15_inventario.py --pacchetto        # cartella + zip da mandare per mail

--pacchetto [CARTELLA] (default ~/Desktop) crea <CARTELLA>/inventario_AAAA-MM-GG/ con inventario.txt (il rapporto) e
inventario.csv (per Excel/Numbers) e lo zip inventario_AAAA-MM-GG.zip accanto, pronto da allegare.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
import unicodedata
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

PEZZI_PER_SET = Decimal(4)

SQL_LOTTI = """SELECT l.public_id, s.fornitore, s.referenza_commerciale, l.numero_lotto_produttore, l.data_ricezione,
       l.data_scadenza, l.quantita_iniziale, l.quantita_residua, l.unita_misura::text, l.anomalia,
       COALESCE((SELECT string_agg(DISTINCT v.denominazione, ', ' ORDER BY v.denominazione)
                 FROM tpo.semine se JOIN tpo.varieta v ON v.id=se.varieta_id WHERE se.lotto_seme_id=l.id), '')
FROM tpo.lotti_seme l JOIN tpo.sementi s ON s.id=l.semente_id
ORDER BY lower(s.referenza_commerciale), lower(s.fornitore), l.data_ricezione, l.public_id"""

SQL_ARTICOLI = """SELECT a.public_id, a.denominazione, a.unita_misura::text, COALESCE(st.disponibile, 0),
       (SELECT max(m.data_movimento) FROM tpo.movimenti_magazzino m WHERE m.articolo_id=a.id)
FROM tpo.articoli a LEFT JOIN tpo.stock_articoli st ON st.articolo_id=a.id
ORDER BY lower(a.denominazione), a.public_id"""


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def _n(value) -> str:
    text = format(Decimal(value).normalize(), "f")
    return text


def _semine_in_corso_module():
    path = Path(__file__).resolve().parent / "2026-10-16_semine_in_corso.py"
    spec = importlib.util.spec_from_file_location("semine_in_corso", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pacchetto(conn, destinazione: str | None = None, oggi: date | None = None, out=print) -> int:
    """Cartella inventario_AAAA-MM-GG/ (txt + csv) e il suo zip, pronti da allegare a una mail."""
    oggi = oggi or date.today()
    base = Path(destinazione).expanduser() if destinazione else Path.home() / "Desktop"
    nome = f"inventario_{oggi.isoformat()}"
    cartella = base / nome
    cartella.mkdir(parents=True, exist_ok=True)
    righe: list[str] = []
    run(conn, str(cartella / "inventario.csv"), out=righe.append)
    testo = "\n".join(righe) + "\n"
    (cartella / "inventario.txt").write_text(f"Tower Power - inventario del {oggi:%d/%m/%Y}\n\n{testo}", encoding="utf-8")
    archivio = base / f"{nome}.zip"
    with zipfile.ZipFile(archivio, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(cartella.iterdir()):
            z.write(f, f"{nome}/{f.name}")
    out(testo.rstrip())
    out(f"\nCARTELLA: {cartella}")
    out(f"ZIP_PER_MAIL: {archivio}")
    return 0


def run(conn, csv_path: str | None = None, out=print) -> int:
    cur = conn.cursor()
    cur.execute(SQL_LOTTI)
    lotti = cur.fetchall()
    cur.execute(SQL_ARTICOLI)
    articoli = cur.fetchall()
    righe_csv = []

    out("== INVENTARIO (sola lettura: numeri del SISTEMA, non conteggio fisico)")
    out("\n-- SEMI: lotti")
    out("lotto | fornitore | referenza | lotto produttore | ricevuto | scade | iniziale | RESIDUO | seminato per | anomalia")
    per_referenza: dict[str, Decimal] = {}
    totale = Decimal(0)
    for lse, forn, ref, num, ric, sca, ini, res, uom, anom, varieta in lotti:
        out(f"{lse} | {forn} | {ref} | {num} | {ric:%d/%m/%Y} | {sca.strftime('%d/%m/%Y') if sca else '-'} | "
            f"{_n(ini)} {uom} | {_n(res)} {uom} | {varieta or '-'} | {anom or '-'}")
        per_referenza[ref] = per_referenza.get(ref, Decimal(0)) + Decimal(res)
        totale += Decimal(res)
        righe_csv.append(["SEME", lse, f"{forn} - {ref}", num, _n(ini), _n(res), uom, varieta, anom or "", "",
                          sca.isoformat() if sca else ""])
    if not lotti:
        out("   nessun lotto di seme a sistema")
    out("\nResiduo per referenza (somma dei suoi lotti):")
    for ref, qty in sorted(per_referenza.items(), key=lambda kv: _fold(kv[0])):
        out(f"   {ref}: {_n(qty)} g")
    out(f"   TOTALE semi residui a sistema: {_n(totale)} g in {len(lotti)} lotti")

    out("\n-- MATERIALI: articoli di magazzino")
    out("articolo | denominazione | giacenza | ultimo movimento | SET possibili")
    for art, nome, uom, disp, ultimo in articoli:
        f = _fold(nome)
        sets = ""
        if uom == "UNIT" and ("vaschett" in f or "substrat" in f):
            sets = f"{_n(Decimal(disp) / PEZZI_PER_SET)} SET"
        out(f"{art} | {nome} | {_n(disp)} {uom} | {ultimo.strftime('%d/%m/%Y') if ultimo else '-'} | {sets or '-'}")
        righe_csv.append(["MATERIALE", art, nome, "", "", _n(disp), uom, "", "",
                          ultimo.date().isoformat() if ultimo else "", sets])
    if not articoli:
        out("   nessun articolo a sistema")
    out("\nRegola di consumo: 4 vaschette + 4 substrati per SET seminato.")

    sic = _semine_in_corso_module()
    semine = sic.leggi(cur)
    out("\n-- SEMINE IN CORSO (SET attesi registrati sulle semine)")
    in_semina = [x for x in semine if x["stato"] in sic.IN_SEMINA]
    out(f"TOTALE SET IN SEMINA (germinazione + luce + crescita): {_n(sic.totale(in_semina))} SET in {len(in_semina)} semine")
    for stadio in sic.IN_SEMINA:
        lista = [x for x in in_semina if x["stato"] == stadio]
        out(f"   {stadio}: {_n(sic.totale(lista))} SET in {len(lista)} semine")
    per_varieta: dict[str, Decimal] = {}
    for x in in_semina:
        if x["set"] is not None:
            per_varieta[x["varieta"]] = per_varieta.get(x["varieta"], Decimal(0)) + x["set"]
    out("Per varieta' (in semina): " + (", ".join(f"{v} {_n(q)}" for v, q in sorted(per_varieta.items(), key=lambda kv: _fold(kv[0])))
                                         or "-"))
    senza = [x["id"] for x in in_semina if x["set"] is None]
    if senza:
        out("   attenzione, SET ? (resa attesa non compilata, non contati): " + ", ".join(senza))
    for stadio, titolo in (("AVVIATA", "Appena avviate (non ancora in germinazione)"),
                           ("PRONTA_ALLA_RACCOLTA", "Pronte alla raccolta (non incluse nel totale sopra)")):
        lista = [x for x in semine if x["stato"] == stadio]
        out(f"{titolo}: {_n(sic.totale(lista))} SET in {len(lista)} semine")
    for x in semine:
        righe_csv.append(["SEMINA_IN_CORSO", x["id"], x["varieta"], x["codice"], "", _n(x["set"]) if x["set"] is not None else "",
                          "SET", x["stato"], "", x["avvio"].date().isoformat(), ""])
    righe_csv.append(["TOTALE_SET_IN_SEMINA", "", "germinazione + luce + crescita", "", "", _n(sic.totale(in_semina)),
                      "SET", "", "", "", ""])

    if csv_path:
        path = Path(csv_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["tipo", "id", "descrizione", "lotto_produttore", "iniziale", "giacenza_o_residuo", "unita",
                             "seminato_per", "anomalia", "ultimo_movimento", "set_possibili_o_scadenza"])
            for row in righe_csv:
                writer.writerow(row[:9] + [row[9], row[10]])
        out(f"\nFile CSV scritto: {path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", metavar="FILE", help="scrive anche un file CSV (apribile con Excel/Numbers)")
    ap.add_argument("--pacchetto", nargs="?", const="", metavar="CARTELLA",
                    help="crea cartella + zip da mandare per mail (default sul Desktop)")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"], autocommit=True)
    try:
        if a.pacchetto is not None:
            return pacchetto(conn, a.pacchetto or None)
        return run(conn, a.csv)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
