"""Pagamento delle consegne ("pagato / da pagare") - 11/10/2026, richiesta di Matteo.

Tre usi (uno per volta). Senza --esegui NON scrive nulla (anteprima).

1) --storico : le consegne GIA' FATTE (CON-000001...) risultano tutte "da pagare" perche' il sistema non ne sapeva
   nulla. Matteo le dichiara tutte pagate, con la stessa data e lo stesso metodo ("dati non rilevanti ora, mi
   interessa tenere il controllo da ora"). Per onesta' vengono registrate con il segno STORICO: la data salvata e'
   quella della DICHIARAZIONE (default: oggi), il metodo e' ALTRO (segnaposto) e la nota dice che data e metodo
   reali non sono stati registrati. Sulla bolla compare "PAGADO - registrado el <data> (entrega anterior al control
   de pagos)", mai un metodo o una data di incasso inventati.
     .venv/bin/python scripts/commissioning/2026-10-11_pagamenti_consegne.py --storico            # anteprima
     .venv/bin/python scripts/commissioning/2026-10-11_pagamenti_consegne.py --storico --esegui
   Opzioni: --data AAAA-MM-GG (default oggi)   --metodo BONIFICO|CONTANTI|CARTA|BIZUM|ALTRO (default ALTRO)
            --escludi-clienti NOME [NOME ...]  clienti che NON hanno pagato: le loro consegne restano DA PAGARE
            --escludi-consegne CON-... [CON-...]  singole consegne che NON sono state pagate (resta DA PAGARE)
     (11/10: --escludi-clienti Bahia Tagoro "Azul y Sal")

2) --pagata CON-... [CON-...] --metodo M [--data AAAA-MM-GG] [--importo 12.50] : pagamento vero di una o piu'
   consegne (data = oggi se non indicata; l'importo e' facoltativo e solo per una consegna).
     ... --pagata CON-000012 --metodo CONTANTI --esegui

3) --annulla PGC-000003 [PGC-...] : annulla uno o piu' pagamenti registrati per errore (restano nello storico;
   poi si puo' registrare quello giusto).

A fine esecuzione stampa sempre il COMANDO CORRETTIVO pronto da copiare (annulla esattamente cio' che ha appena
registrato), e in anteprima la forma generica.

Dopo ogni registrazione le bolle delle consegne interessate vengono rigenerate (--sovrascrivi) nella cartella del
cliente (default ~/Desktop/bolle), cosi' il PDF dice PAGADO. --senza-bolle per saltarle.
Rilanciabile: una consegna gia' pagata viene saltata e lo dice; chiavi di idempotenza fisse.
Richiede la migrazione 20261010_0038 (migrate_to_head.sh): senza, si ferma.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

BASE_SCRIPT = ROOT / "scripts" / "commissioning" / "2026-10-08_consegne_giornata.py"
TAG = "pagamenti-consegne-2026-10-11"
HEAD = "20261010_0038"
LOCAL_TZ = ZoneInfo("Atlantic/Canary")
METODI = ("BONIFICO", "CONTANTI", "CARTA", "BIZUM", "ALTRO")
PDF_DIR_DEFAULT = Path.home() / "Desktop" / "bolle"

CONSEGNE = """
SELECT c.public_id, cl.denominazione, c.data_effettiva,
       (SELECT count(*) FROM tpo.pagamenti_consegna p WHERE p.consegna_id=c.id AND p.tipo='PAGAMENTO'),
       (SELECT p.public_id FROM tpo.pagamenti_consegna p WHERE p.consegna_id=c.id AND p.tipo='PAGAMENTO'
          AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna a WHERE a.annulla_pagamento_id=p.id))
FROM tpo.consegne c JOIN tpo.clienti cl ON cl.id=c.cliente_id
WHERE c.stato='CONSEGNATA' ORDER BY c.public_id"""


_BASE = None


def carica_base():
    global _BASE
    if _BASE is not None:
        return _BASE
    spec = importlib.util.spec_from_file_location("consegne_giornata_base", BASE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.HEAD = HEAD
    _BASE = module
    return module


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn").strip()


def oggi() -> date:
    return datetime.now(LOCAL_TZ).date()


def _storico_note(data: date) -> str:
    return (f"Pagamento dichiarato da Matteo il {data.isoformat()} all'avvio del controllo pagamenti: "
            "data e metodo reali del pagamento non sono stati registrati.")


def stato_consegne(ctx):
    """[(consegna, cliente, data_effettiva, n_pagamenti_registrati, pagamento_attivo|None)]"""
    return ctx.q(CONSEGNE)


def comandi_pagamento(con, data, metodo, importo, note, storico, tentativo):
    key = f"{TAG}-{con}-n{tentativo}"
    args = ["pagamento-consegna", "registra", "--consegna", con, "--data", data.isoformat(), "--metodo", metodo]
    if importo is not None:
        args += ["--importo", importo]
    if note:
        args += ["--note", note]
    if storico:
        args.append("--storico")
    args += ["--actor", "matteo", "--reason",
             "Pagamento consegna dichiarato da Matteo (controllo pagamenti dall'11/10/2026)",
             "--correlation-id", key, "--idempotency-key", key]
    return args


def rigenera_bolla(ctx, con, pdf_dir):
    pdf_dir.mkdir(parents=True, exist_ok=True)
    ctx.tpo(["bolla", "genera", "--consegna", con, "--output-dir", str(pdf_dir), "--per-cliente",
             "--sovrascrivi"], f"bolla PDF {con} (rigenerata)")


SELF = "scripts/commissioning/2026-10-11_pagamenti_consegne.py"
PY = ".venv/bin/python"


def run(ctx, a) -> int:
    ctx.check_head()
    righe = {r[0]: r for r in stato_consegne(ctx)}
    print(f"== PAGAMENTI CONSEGNE -- {'ESECUZIONE' if ctx.execute else 'ANTEPRIMA (nulla viene scritto)'}")
    print(f"   consegne effettuate a sistema: {len(righe)}; gia' pagate: "
          f"{sum(1 for r in righe.values() if r[4])}; da pagare: {sum(1 for r in righe.values() if not r[4])}")
    if a.annulla:
        return _annulla(ctx, a)
    return _registra(ctx, a, righe)


def _annulla(ctx, a) -> int:
    correttivi = []
    for originale in a.annulla:
        row = ctx.one("""SELECT p.tipo, c.public_id, p.data_pagamento, p.metodo, p.importo,
                                (SELECT x.public_id FROM tpo.pagamenti_consegna x WHERE x.annulla_pagamento_id=p.id)
                         FROM tpo.pagamenti_consegna p JOIN tpo.consegne c ON c.id=p.consegna_id
                         WHERE p.public_id=%s""", (originale,))
        if not row or row[0] != "PAGAMENTO":
            ctx_stop(f"{originale} non e' un pagamento consegna registrato.")
        if row[5]:
            print(f"\n-- {originale} (consegna {row[1]}): gia' annullato ({row[5]}), salto.")
            continue
        key = f"{TAG}-annulla-{originale}"
        ctx.tpo(["pagamento-consegna", "annulla", "--originale", originale,
                 "--actor", "matteo", "--reason", "Pagamento consegna registrato per errore (dichiarato da Matteo)",
                 "--correlation-id", key, "--idempotency-key", key],
                f"annulla {originale} (consegna {row[1]}, {row[2]}, {row[3]})")
        if not a.senza_bolle:
            rigenera_bolla(ctx, row[1], Path(a.pdf_dir))
        extra = f" --importo {row[4]}" if row[4] is not None else ""
        correttivi.append(f"{PY} {SELF} --pagata {row[1]} --metodo {row[3]} --data {row[2].isoformat()}{extra} --esegui")
    if correttivi:
        print("\nCOMANDO CORRETTIVO (per rimettere pagato quanto hai appena annullato):")
        for line in correttivi:
            print(f"  {line}")
    return _fine(ctx)


def _registra(ctx, a, righe) -> int:
    data = date.fromisoformat(a.data) if a.data else oggi()
    if a.storico:
        metodo, importo, storico, note = a.metodo or "ALTRO", None, True, _storico_note(data)
        escludi = a.escludi_clienti or []
        escludi_con = a.escludi_consegne or []
        ignote = [c for c in escludi_con if c not in righe]
        if ignote:
            ctx_stop(f"--escludi-consegne: consegne non effettuate o inesistenti: {', '.join(ignote)}.")
        for pattern in escludi:
            if not any(_fold(pattern) in _fold(r[1]) for r in righe.values()):
                ctx_stop(f"--escludi-clienti: nessun cliente con consegne effettuate assomiglia a '{pattern}'.")
        scelte = []
        for con, r in righe.items():
            if r[4]:
                continue
            if con in escludi_con or any(_fold(p) in _fold(r[1]) for p in escludi):
                print(f"   ESCLUSA {con} ({r[1]}): resta DA PAGARE")
                continue
            scelte.append(con)
        print(f"\nDichiarazione STORICA: pagate {len(scelte)} consegne, data {data.isoformat()}, metodo {metodo}, "
              "senza importo.")
        print("   (data = giorno della dichiarazione, NON il giorno vero del pagamento; sulla bolla comparira' "
              "'registrado el ...')")
    else:
        metodo, importo, storico, note = a.metodo, a.importo, False, a.note
        if importo is not None and len(a.pagata) != 1:
            ctx_stop("--importo si indica solo con una consegna (--pagata CON-...).")
        sconosciute = [c for c in a.pagata if c not in righe]
        if sconosciute:
            ctx_stop(f"consegne non effettuate o inesistenti: {', '.join(sconosciute)}.")
        scelte = list(a.pagata)

    if not scelte:
        print("\nNiente da registrare: tutte le consegne scelte sono gia' pagate.")
    nuove, elaborate = [], []
    for con in scelte:
        _, cliente, effettiva, n_prec, attivo = righe[con]
        elaborate.append(con)
        if attivo:
            print(f"\n-- {con} ({cliente}): gia' pagata ({attivo}), salto.")
            continue
        ctx.tpo(comandi_pagamento(con, data, metodo, importo, note, storico, n_prec + 1),
                f"pagamento {con} ({cliente}, consegnata il {effettiva:%d/%m/%Y})")
        nuove.append(con)
    if not a.senza_bolle:
        for con in elaborate:
            rigenera_bolla(ctx, con, Path(a.pdf_dir))

    print("\nCOMANDO CORRETTIVO (se qualcosa non torna, annulla esattamente quanto registrato qui):")
    if ctx.execute and nuove:
        ids = [r[0] for r in ctx.q(
            """SELECT p.public_id FROM tpo.pagamenti_consegna p JOIN tpo.consegne c ON c.id=p.consegna_id
               WHERE c.public_id = ANY(%s) AND p.tipo='PAGAMENTO'
                 AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna x WHERE x.annulla_pagamento_id=p.id)
               ORDER BY p.public_id""", (nuove,))]
        print(f"  {PY} {SELF} --annulla {' '.join(ids)} --esegui")
    elif ctx.execute:
        print("  (nulla di nuovo registrato: niente da annullare)")
    else:
        print(f"  {PY} {SELF} --annulla PGC-000001 [PGC-...] --esegui    "
              "(gli id esatti te li stampo a fine esecuzione)")
    return _fine(ctx)


def _fine(ctx) -> int:
    print("\n== FINE" + ("" if ctx.execute else " (anteprima: per scrivere aggiungi --esegui)"))
    return 0

def ctx_stop(message):
    raise carica_base().Stop(message)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    uso = ap.add_mutually_exclusive_group(required=True)
    uso.add_argument("--storico", action="store_true", help="dichiara pagate tutte le consegne gia' fatte")
    uso.add_argument("--pagata", nargs="+", metavar="CON-000000", help="consegne pagate (pagamento vero)")
    uso.add_argument("--annulla", nargs="+", metavar="PGC-000000", help="annulla pagamenti registrati per errore")
    ap.add_argument("--escludi-clienti", nargs="+", metavar="NOME",
                    help="con --storico: clienti che NON hanno pagato (le loro consegne restano DA PAGARE)")
    ap.add_argument("--escludi-consegne", nargs="+", metavar="CON-000000",
                    help="con --storico: singole consegne che NON sono state pagate")
    ap.add_argument("--data", help="data AAAA-MM-GG (default oggi)")
    ap.add_argument("--metodo", choices=METODI)
    ap.add_argument("--importo", help="importo facoltativo, solo con una consegna (es. 12.50)")
    ap.add_argument("--note")
    ap.add_argument("--pdf-dir", default=str(PDF_DIR_DEFAULT))
    ap.add_argument("--senza-bolle", action="store_true", help="non rigenerare le bolle PDF")
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    return ap


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    if a.pagata and not a.metodo:
        print("STOP: con --pagata serve --metodo.", file=sys.stderr)
        return 2
    if a.data and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.data):
        print("STOP: --data deve essere AAAA-MM-GG.", file=sys.stderr)
        return 2
    base = carica_base()
    ctx = base.Ctx(a.esegui, Path(a.pdf_dir))
    try:
        return run(ctx, a)
    except base.Stop as exc:
        print(f"\nSTOP: {exc}", file=sys.stderr)
        return 1
    finally:
        ctx.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
