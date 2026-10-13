"""Registra le semine REALI dichiarate da Matteo il 12/10/2026 (stessa procedura governata dell'11/10).

Stamattina alle 09:00 sono stati seminati 1 SET ciascuno di: Amaranto, Hinojo, Albahaca (nel sistema "Basilico"),
Col roja (nel sistema "Cavolo rosso"), Pak Choi, Girasol (nel sistema "Girasole").

L'avvio fisico registrato e' l'ora di semina (09:00, ora Canarie). Per ogni semina: `tpo semina commission` (stato AVVIATA,
grammi = g/SET del protocollo approvato x SET, lotto di seme MOSTRATO prima di scrivere; codice AAA-GGMM-L e SEM-...
li genera il sistema) e consumo materiali (4 vaschette + 4 substrati per SET). Nessun cambio di stadio oltre AVVIATA.

Si ferma SENZA scrivere nulla (prima di qualsiasi semina) se per una varieta' manca un protocollo approvato corrente o un
lotto di seme con residuo sufficiente: in quel caso lo dice e le altre non vengono scritte a meta'.
Senza --esegui NON scrive nulla (anteprima). Rilanciabile: una semina gia' registrata viene saltata.
A fine esecuzione stampa il COMANDO CORRETTIVO per ogni semina creata.

Uso, dalla cartella del progetto:
  .venv/bin/python scripts/commissioning/2026-10-12_semine.py                  # anteprima
  .venv/bin/python scripts/commissioning/2026-10-12_semine.py --esegui
  Opzioni: --riga "Varieta:SET" (ripetibile; sostituisce l'elenco di oggi)  --ora HH:MM (default 09:00)
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

BASE = ROOT / "scripts" / "commissioning" / "2026-10-11_semine.py"
GIORNO = date(2026, 10, 12)
ORA = "09:00"
PY = ".venv/bin/python"
# (nome ESATTO a sistema, SET)
OGGI = [("Amaranto", 1), ("Hinojo", 1), ("Basilico", 1), ("Cavolo rosso", 1), ("Pak Choi", 1), ("Girasole", 1)]


def carica_base():
    spec = importlib.util.spec_from_file_location("semine_11_base", BASE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def voci(righe: list[str] | None, ora: str, giorno: date = GIORNO):
    if not righe:
        return [(nome, n, giorno, ora) for nome, n in OGGI]
    out = []
    for item in righe:
        nome, _, n = item.rpartition(":")
        if not nome or not n.isdigit() or int(n) <= 0:
            raise SystemExit(f"STOP: riga '{item}' non valida (formato Varieta:SET con SET intero > 0).")
        out.append((nome, int(n), giorno, ora))
    return out


def run(conn, esegui: bool, righe=None, ora=ORA, adesso: datetime | None = None, mattina=None, base=None,
        giorno: date = GIORNO) -> int:
    b = base or carica_base()
    m = mattina or b.carica()
    elenco = voci(righe, ora, giorno)
    errore = b.controlla_passato(elenco, adesso or datetime.now(b.TZ))
    if errore:
        print(f"STOP: {errore}", file=sys.stderr)
        return 1
    nomi = [b.risolvi_varieta(conn, nome) for nome, *_ in elenco]
    print(f"== SEMINE {giorno:%d/%m/%Y} -- {'ESECUZIONE' if esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    # prima fase, SEMPRE in anteprima e su TUTTE le varieta': raccoglie chi non ha protocollo approvato o seme sufficiente
    # (una che si ferma non blocca il controllo delle altre, cosi' vedi subito tutti i problemi insieme)
    mancanti, anteprima, motivi = [], [], []
    for nome, (_, n_set, giorno, ora_) in zip(nomi, elenco):
        m.SEMINE = [(nome, n_set)]
        try:
            anteprima += m.run(conn, False, ora_, giorno)
        except SystemExit as exc:
            mancanti.append(nome)
            motivi.append(f"  - {nome}: {exc.code}")
    if mancanti:
        ok = [f'--riga "{n}:{k}"' for n, (_, k, *_r) in zip(nomi, elenco) if n not in mancanti]
        print("\n== NON POSSO SEMINARE (manca un protocollo approvato corrente o seme sufficiente): "
              + ", ".join(mancanti), file=sys.stderr)
        print("\n".join(motivi), file=sys.stderr)
        print("Nulla e' stato scritto." + (" Per registrare solo le altre:\n  "
              f"{PY} scripts/commissioning/2026-10-12_semine.py " + " ".join(ok) + " [--esegui]" if ok else ""),
              file=sys.stderr)
        return 1
    if not esegui:
        print("\n-- tutte le varieta' hanno protocollo e seme: anteprima completa sopra --")
    else:
        print("\n-- controllo superato su tutte le varieta': scrivo --")
    risultati = anteprima
    if esegui:
        risultati = []
        for nome, (_, n_set, giorno, ora_) in zip(nomi, elenco):
            m.SEMINE = [(nome, n_set)]
            risultati += m.run(conn, True, ora_, giorno)
    print("\n== RIEPILOGO")
    for nome, n_set, semina, codice in risultati:
        print(f"  {nome:14} {n_set} SET  {semina}  {codice}")
    print("\nCOMANDO CORRETTIVO (una semina registrata non si modifica ne' si cancella: se qualcosa non torna "
          "la si chiude come 'interruzione' e si registra quella giusta; dimmelo e preparo io il resto):")
    if esegui:
        for _, _, semina, _ in risultati:
            print(f"  {b.correttivo(semina)}")
    else:
        print(f"  {b.correttivo('SEM-000000')}    (i numeri SEM esatti te li stampo a fine esecuzione)")
    print("\n== FINE" + ("" if esegui else " (anteprima: nulla scritto; per scrivere aggiungi --esegui)"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    ap.add_argument("--riga", action="append", help="Varieta:SET (ripetibile)")
    ap.add_argument("--ora", default=ORA)
    ap.add_argument("--giorno", default=None, help="AAAA-MM-GG della semina (default: 12/10/2026)")
    a = ap.parse_args()
    b = carica_base()
    m = b.carica()
    conn = m.base.db()
    conn.autocommit = True
    try:
        return run(conn, a.esegui, a.riga, a.ora, mattina=m, base=b,
                   giorno=date.fromisoformat(a.giorno) if a.giorno else GIORNO)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
