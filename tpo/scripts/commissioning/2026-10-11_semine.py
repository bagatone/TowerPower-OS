"""Registra le semine REALI dichiarate da Matteo l'11/10/2026 (stessa procedura governata del 6/10):

  Rabano  3 SET : messo ieri sera 10/10/2026 ore 21:00
  Cilantro 7 SET: idratato una notte, messo in germinazione stamattina 11/10/2026 ore 09:00
  Afila         : in idratazione; passa a germinazione stasera ore 21:00 -> NON si registra finche' non e'
                  successo (e servono i SET): --afila N, consentito solo dopo le 21:00 (ora Canarie).

L'avvio fisico registrato e' l'ora in cui il seme e' stato messo (germinazione), non l'inizio dell'idratazione
(regola del codice di tracciabilita': conta la data fisica di semina). Per ogni semina: `tpo semina commission`
(stato AVVIATA, grammi = g/SET del protocollo approvato x SET, lotto di seme MOSTRATO prima di scrivere; codice
AAA-GGMM-L e SEM-... li genera il sistema) e consumo materiali (4 vaschette + 4 substrati per SET).
Nessun cambio di stadio oltre AVVIATA (si fa solo su tua parola, come per i passaggi a luce).

Senza --esegui NON scrive nulla (anteprima). Rilanciabile: una semina gia' registrata viene saltata.
A fine esecuzione stampa il COMANDO CORRETTIVO per ogni semina creata.

Uso, dalla cartella del progetto:
  .venv/bin/python scripts/commissioning/2026-10-11_semine.py                 # anteprima
  .venv/bin/python scripts/commissioning/2026-10-11_semine.py --esegui
  .venv/bin/python scripts/commissioning/2026-10-11_semine.py --afila 5       # stasera, dopo le 21:00
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

TZ = timezone(timedelta(hours=1))      # Canarie, ora legale fino al 25/10/2026
MATTINA = ROOT / "scripts" / "commissioning" / "2026-10-06_semine_mattina.py"
PY, CHIUDI = ".venv/bin/python", "scripts/commissioning/2026-10-05_chiudi_semina.py"

# (varieta', SET dichiarati da Matteo, giorno, ora fisica)
FISSE = [("Rabano", 3, date(2026, 10, 10), "21:00"),
         ("Cilantro", 7, date(2026, 10, 11), "09:00")]
AFILA_GIORNO, AFILA_ORA = date(2026, 10, 11), "21:00"


def carica():
    spec = importlib.util.spec_from_file_location("semine_mattina", MATTINA)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn").strip()


def risolvi_varieta(conn, nome: str) -> str:
    """Nome ESATTO della varieta' a sistema (senza accenti/maiuscole: "Rabano" -> la denominazione vera)."""
    cur = conn.cursor()
    cur.execute("SELECT denominazione FROM tpo.varieta")
    nomi = [r[0] for r in cur.fetchall()]
    esatti = [n for n in nomi if _fold(n) == _fold(nome)]
    simili = esatti or [n for n in nomi if _fold(n).startswith(_fold(nome))]
    if len(simili) != 1:
        print(f"STOP: varieta' '{nome}': trovate {len(simili)} corrispondenze a sistema "
              f"({', '.join(simili) or 'nessuna'}).", file=sys.stderr)
        raise SystemExit(1)
    return simili[0]


def elenco(afila: int | None):
    voci = list(FISSE)
    if afila is not None:
        voci.append(("Afila", afila, AFILA_GIORNO, AFILA_ORA))
    return voci


def controlla_passato(voci, adesso: datetime) -> str | None:
    """Una semina non ancora avvenuta non si registra (nessuna data inventata o anticipata)."""
    for nome, _, giorno, ora in voci:
        h, m = (int(x) for x in ora.split(":"))
        inizio = datetime(giorno.year, giorno.month, giorno.day, h, m, tzinfo=TZ)
        if inizio > adesso:
            return (f"{nome}: l'avvio dichiarato ({inizio:%d/%m/%Y %H:%M}) e' nel futuro rispetto a ora "
                    f"({adesso:%d/%m/%Y %H:%M}): registrala dopo che e' successo.")
    return None


def correttivo(semina: str) -> str:
    return (f"{PY} {CHIUDI} --semina {semina} --esito interruzione --venduti 0 --scartati 0 --esegui")


def run(conn, esegui: bool, afila: int | None, adesso: datetime | None = None, mattina=None) -> int:
    m = mattina or carica()
    voci = elenco(afila)
    errore = controlla_passato(voci, adesso or datetime.now(TZ))
    if errore:
        print(f"STOP: {errore}", file=sys.stderr)
        return 1
    print(f"== SEMINE 10-11/10/2026 -- {'ESECUZIONE' if esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    risultati = []
    for nome, n_set, giorno, ora in voci:
        nome = risolvi_varieta(conn, nome)
        m.SEMINE = [(nome, n_set)]
        risultati += m.run(conn, esegui, ora, giorno)
    print("\n== RIEPILOGO")
    for nome, n_set, semina, codice in risultati:
        print(f"  {nome:10} {n_set} SET  {semina}  {codice}")
    print("\nCOMANDO CORRETTIVO (una semina registrata non si modifica ne' si cancella: se qualcosa non torna "
          "la si chiude come 'interruzione' e si registra quella giusta; dimmelo e preparo io il resto):")
    if esegui:
        for _, _, semina, _ in risultati:
            print(f"  {correttivo(semina)}")
    else:
        print(f"  {correttivo('SEM-000000')}    (i numeri SEM esatti te li stampo a fine esecuzione)")
    print("\n== FINE" + ("" if esegui else " (anteprima: nulla scritto; per scrivere aggiungi --esegui)"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    ap.add_argument("--afila", type=int, metavar="SET", help="SET di Afila messi in germinazione (dopo le 21:00)")
    a = ap.parse_args()
    if a.afila is not None and a.afila <= 0:
        print("STOP: --afila richiede un numero intero di SET maggiore di zero.", file=sys.stderr)
        return 2
    m = carica()
    conn = m.base.db()
    conn.autocommit = True
    try:
        return run(conn, a.esegui, a.afila, mattina=m)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
