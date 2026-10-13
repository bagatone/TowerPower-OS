"""Nuovo cliente CLANDESTINO (locale a Puerto del Rosario) - registrazione dell'11/10/2026, richiesta di Matteo.

Registra, in quest'ordine (ogni passo e' idempotente: se rilanci, salta cio' che e' gia' fatto):
  1. il cliente Clandestino (senza dati fiscali, che si aggiungono quando Matteo li ha; "Puerto del Rosario" sta nel
     motivo registrato);
  2. la dichiarazione di Matteo "Cilantro SEM-000013 pronto alla raccolta" (2 SET rimasti in luce, passaggio
     CRESCITA +1 minuto dopo la luce, poi PRONTA_ALLA_RACCOLTA alle 09:50 del 10/10);
  3. le raccolte del 10/10 alle 10:00 con carico a magazzino: Cilantro 1 SET (SEM-000013), Afila 0.5 SET
     (SEM-000010), Rabano 0.5 SET (SEM-000015);
  4. l'ordine manuale di Clandestino del 10/10 e la consegna (10:05) con la provenienza di ogni riga;
  5. la bolla PDF in <pdf-dir>/clandestino/ (default ~/Desktop/bolle);
  6. il pagamento alla consegna (vero, non storico, data 10/10) SE indichi --metodo; altrimenti lo script ti lascia
     il comando pronto da lanciare quando mi dici il metodo (nessun metodo viene inventato);
  7. il programma ricorrente: ogni giovedi' a partire dal 15/10/2026, 1 SET di Cilantro fisso. Le altre due mezze
     varieta' le aggiungi tu piano piano (nuova versione del programma). --senza-programma per saltarlo.

ORARI STIMATI: il 10/10 non hai annotato l'ora; 09:50 (pronta), 10:00 (raccolte), 10:05 (consegna) sono stime
dichiarate come tali nei motivi registrati. Cambiabili con --ora-pronta / --ora-raccolta / --ora-consegna (HH:MM).

Sempre in ANTEPRIMA finche' non aggiungi --esegui. Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-11_clandestino.py                       # anteprima
  .venv/bin/python scripts/commissioning/2026-10-11_clandestino.py --metodo CONTANTI     # anteprima con pagamento
  .venv/bin/python scripts/commissioning/2026-10-11_clandestino.py --metodo CONTANTI --esegui

Si ferma (senza scrivere altro) se: la migrazione non e' 20261010_0038; SEM-000013 non e' un Cilantro da 2 SET attesi in
LUCE/CRESCITA/PRONTA; una raccolta supera i SET attesi; la giacenza di una varieta' non e' 0 prima del carico.

COMANDI CORRETTIVI (stampati anche a fine esecuzione con gli id esatti):
  pagamento sbagliato (metodo/data):  .venv/bin/python scripts/commissioning/2026-10-11_pagamenti_consegne.py --annulla PGC-...
                                      poi si registra quello giusto con --pagata CON-... --metodo M --data AAAA-MM-GG
  consegna / raccolte / programma:    le consegne CONSEGNATE sono immutabili e le raccolte sono registrazioni di
                                      autorita': se qualcosa e' sbagliato dimmelo, preparo la correzione governata.
"""
from __future__ import annotations

import argparse
import difflib
import importlib.util
import sys
import unicodedata
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

BASE_SCRIPT = ROOT / "scripts" / "commissioning" / "2026-10-08_consegne_giornata.py"
PROGRAMMA_SCRIPT = ROOT / "scripts" / "commissioning" / "2026-10-08_nuovo_programma.py"
TAG = "clandestino-2026-10-10"
HEAD = "20261010_0038"
LOCAL_TZ = ZoneInfo("Atlantic/Canary")
GIORNO = date(2026, 10, 10)
CLIENTE = "Clandestino"
METODI = ("BONIFICO", "CONTANTI", "CARTA", "BIZUM", "ALTRO")
WORK = ROOT / "outputs" / "clandestino_2026_10_10"
PDF_DIR_DEFAULT = Path.home() / "Desktop" / "bolle"

# (semina, varieta, SET attesi a sistema = SET dichiarati pronti da Matteo)
PRONTA = ("SEM-000013", "Cilantro", "2")
# (varieta, SET, semina di provenienza)
VOCI = [("Cilantro", "1", "SEM-000013"), ("Afila", "0.5", "SEM-000010"), ("Rabano", "0.5", "SEM-000015")]
PROGRAMMA_PRIMA = date(2026, 10, 15)          # giovedi'
PROGRAMMA_RIGHE = ["Cilantro:1"]
PROGRAMMA_OGNI_GIORNI = 7
SELF = "scripts/commissioning/2026-10-11_clandestino.py"

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
    module.TAG = TAG
    module.OGGI = GIORNO.isoformat()
    module.WORK = WORK
    _BASE = module
    return module


def carica_programma():
    spec = importlib.util.spec_from_file_location("nuovo_programma_base", PROGRAMMA_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").strip()


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def alle(giorno: date, hhmm: str) -> datetime:
    ore, minuti = (int(x) for x in hhmm.split(":"))
    return datetime.combine(giorno, time(ore, minuti), tzinfo=LOCAL_TZ)


class Orari:
    def __init__(self, pronta="09:50", raccolta="10:00", consegna="10:05") -> None:
        self.pronta = alle(GIORNO, pronta)
        self.raccolta = alle(GIORNO, raccolta)
        self.consegna = alle(GIORNO, consegna)
        if not (self.pronta < self.raccolta < self.consegna):
            raise ValueError("gli orari devono essere in ordine: pronta < raccolta < consegna")


# --------------------------------------------------------------------------------------------- cliente
def fase_cliente(b, ctx):
    print(f"\n== CLIENTE {CLIENTE} (nuovo, senza dati fiscali)")
    rows = ctx.q("SELECT public_id, denominazione FROM tpo.clienti")
    esatti = [r for r in rows if _fold(r[1]) == _fold(CLIENTE)]
    if len(esatti) > 1:
        raise b.Stop(f"trovati {len(esatti)} clienti chiamati {CLIENTE}: non scelgo io.")
    if esatti:
        print(f"  gia' esistente: {esatti[0][0]} ({esatti[0][1]})")
        return esatti[0][0]
    simili = [r for r in rows if difflib.SequenceMatcher(None, _fold(r[1]), _fold(CLIENTE)).ratio() >= 0.75]
    for pid, nome in simili:
        print(f"  ATTENZIONE nome simile gia' a sistema: {pid} {nome}: se e' lo stesso cliente ferma tutto "
              "(non rilanciare con --esegui) e dimmelo.")
    nxt = ctx.one("SELECT COALESCE(max(substring(public_id from 5)::int),0)+1 FROM tpo.clienti")[0]
    cid = f"CLI-{int(nxt):06d}"
    ctx.tpo(["onboarding", "customer", "--customer-id", cid, "--denomination", CLIENTE, "--actor", b.ACTOR,
             "--reason", "Nuovo cliente Clandestino (locale a Puerto del Rosario), prima consegna il 10/10/2026; "
                         "dati fiscali non ancora disponibili",
             "--correlation-id", f"{TAG}-cliente"], f"nuovo cliente {CLIENTE} ({cid})")
    return cid


# --------------------------------------------------------------------------------------------- pronta
def fase_pronta(b, ctx, orari: Orari):
    semina, varieta, dichiarati = PRONTA
    print(f"\n== {varieta.upper()} {semina}: dichiarazione di Matteo 'pronto alla raccolta' (orario stimato "
          f"{orari.pronta:%d/%m %H:%M})")
    stato, version, attesi, uom, _, codice, raccolti = b.semina_row(ctx, semina, varieta)
    print(f"  {semina} {codice}: {stato}, attesi {_n(attesi) if attesi is not None else '?'} {uom or ''}, "
          f"gia' raccolti {_n(raccolti)}, dichiarati pronti {dichiarati} SET")
    if stato == "PRONTA_ALLA_RACCOLTA":
        print("  gia' PRONTA_ALLA_RACCOLTA: nulla da fare")
        return
    if attesi is None or uom != "SET" or Decimal(attesi) != Decimal(dichiarati):
        raise b.Stop(f"{semina}: i SET attesi a sistema non coincidono con i {dichiarati} SET dichiarati. "
                     "Non scelgo io: dimmi quale semina e' pronta.")
    if stato not in ("LUCE", "CRESCITA"):
        raise b.Stop(f"{semina} e' {stato}: la fase pronta parte da LUCE o CRESCITA.")
    ultimo = b.ultimo_evento(ctx, semina)
    if ultimo is None:
        raise b.Stop(f"{semina}: nessun evento di ciclo di vita, non posso datare le transizioni.")
    steps = []
    if stato == "LUCE":
        steps.append(("CRESCITA", ultimo + timedelta(minutes=1),
                      "passaggio amministrativo 1 minuto dopo la luce (LUCE e CRESCITA sono lo stesso processo)"))
    steps.append(("PRONTA_ALLA_RACCOLTA", orari.pronta,
                  f"dichiarata da Matteo l'11/10/2026 ({varieta} {dichiarati} SET pronti, l'ultimo raccolto il "
                  "10/10); orario del 10/10 stimato, non osservato"))
    previous = ultimo
    for nome, when, _ in steps:
        if when <= previous:
            raise b.Stop(f"{semina}: {nome} {when:%Y-%m-%d %H:%M} non e' dopo l'ultimo evento "
                         f"{previous:%Y-%m-%d %H:%M}.")
        previous = when
    for nome, when, nota in steps:
        reason = f"Transizione {nome} {semina} del {when:%d/%m/%Y %H:%M}: {nota}"
        ctx.tpo(["semina", "transition", "--semina", semina, "--expected-semina-version", str(version),
                 "--target-state", nome, "--effective-at", when.isoformat(), "--provenance", b.PROV_TRANS,
                 "--actor", b.ACTOR, "--reason", reason,
                 "--correlation-id", f"{TAG}-lifecycle-{semina}-{nome}",
                 "--idempotency-key", f"{TAG}-lifecycle-{semina}-{nome}", "--confirm"], f"{semina} -> {nome}")
        version += 1


# --------------------------------------------------------------------------------------------- raccolte
def verifica_raccolta(b, ctx, orari: Orari, varieta, qty, semina, prima_della_pronta):
    """Controlli di una raccolta; non scrive. Ritorna (done, codice, attesi, raccolti, giacenza)."""
    stato, _, attesi, uom, _, codice, raccolti = b.semina_row(ctx, semina, varieta)
    done = b.audit_fatto(ctx, "RACCOLTA", f"{TAG}-raccolta-{semina}")
    sara_pronta = prima_della_pronta and semina == PRONTA[0] and stato in ("LUCE", "CRESCITA")
    if not done and stato != "PRONTA_ALLA_RACCOLTA" and not sara_pronta:
        raise b.Stop(f"{semina} ({varieta}) e' {stato}, non PRONTA_ALLA_RACCOLTA: dimmi come procedere.")
    ultimo = b.ultimo_evento(ctx, semina)
    if not done and not sara_pronta and ultimo is not None and orari.raccolta <= ultimo:
        raise b.Stop(f"{semina}: la raccolta ({orari.raccolta:%d/%m %H:%M}) non e' dopo l'ultimo evento "
                     f"({ultimo:%Y-%m-%d %H:%M}).")
    giac = b.giacenza_set(ctx, b.varieta_id(ctx, varieta))
    if not done and giac != 0:
        raise b.Stop(f"{varieta}: giacenza {_n(giac)} SET diversa da 0 prima del carico: dimmi come procedere.")
    if not done and attesi is not None and Decimal(raccolti) + Decimal(qty) > Decimal(attesi):
        raise b.Stop(f"{semina}: {_n(raccolti)} gia' raccolti + {qty} superano gli attesi {_n(attesi)} SET.")
    return done, codice, attesi, raccolti, giac


def fase_raccolte(b, ctx, orari: Orari):
    print("\n== RACCOLTE E CARICHI A MAGAZZINO del 10/10 (SET che sono usciti con la consegna)")
    for varieta, qty, semina in VOCI:
        done, codice, attesi, raccolti, giac = verifica_raccolta(b, ctx, orari, varieta, qty, semina,
                                                                 not ctx.execute)
        print(f"\n{varieta}: {qty} SET da {semina} ({codice}); giacenza {_n(giac)}; gia' raccolti {_n(raccolti)} "
              f"su {_n(attesi) if attesi is not None else '?'}" + ("  [raccolta gia' registrata]" if done else ""))
        note = (f"Raccolta {varieta} {qty} SET ({semina}) per la consegna a Clandestino del 10/10/2026, "
                "dichiarata da Matteo l'11/10/2026; orario stimato")
        out = ctx.tpo(["raccolta", "record", "--semina", semina, "--quantity", qty, "--uom", "SET",
                       "--effective-at", orari.raccolta.isoformat(), "--notes", note, "--actor", b.ACTOR,
                       "--reason", note, "--correlation-id", f"{TAG}-raccolta-{semina}",
                       "--idempotency-key", f"{TAG}-raccolta-{semina}", "--confirm"], f"raccolta {varieta}")
        racc = b.kv(out, "RACCOLTA_ID") or done or "RAC-??????(da anteprima)"
        motivo = f"Carico magazzino da raccolta {varieta} {qty} SET ({semina}), consegna Clandestino 10/10"
        ctx.tpo(["movimento", "carica-raccolta", "--raccolta", racc, "--unita-misura", "SET", "--effective-at",
                 orari.raccolta.isoformat(), "--motivo", motivo, "--actor", b.ACTOR, "--reason", motivo,
                 "--correlation-id", f"{TAG}-carico-{semina}", "--idempotency-key", f"{TAG}-carico-{semina}",
                 "--confirm"], f"carico {racc} ({varieta})")


# --------------------------------------------------------------------------------------------- consegna
def fase_consegna(b, ctx, cid, orari: Orari):
    print("\n== ORDINE MANUALE E CONSEGNA a Clandestino (10/10)")
    fatta = b.audit_fatto(ctx, "CONSEGNA", f"{TAG}-consegna-clandestino")
    if fatta:
        print(f"  consegna gia' registrata ({fatta}): salto.")
        return fatta, False
    ord_man, righe_man = b.ordine_manuale(
        ctx, cid, VOCI, "clandestino",
        "Prima vendita a Clandestino (Puerto del Rosario) del 10/10/2026: Cilantro 1 + Afila 0.5 + Rabano 0.5 SET, "
        "pagata alla consegna")
    if ord_man is None:
        print("  (anteprima) consegna: " + " + ".join(f"{v} {q} SET ({s})" for v, q, s in VOCI)
              + " su nuovo ordine manuale")
        return None, False
    righe = b.righe_consegna(ctx, ord_man, righe_man, VOCI)
    con = b.consegna(ctx, cid, GIORNO.isoformat(), orari.consegna.isoformat(), righe, "clandestino",
                     "Consegna a Clandestino del 10/10/2026 (orario stimato): Cilantro 1, Afila 0.5, Rabano 0.5 SET")
    b.bolla(ctx, con)
    return con, True


# --------------------------------------------------------------------------------------------- pagamento
def pagamento_attivo(ctx, con):
    if con is None:
        return None
    row = ctx.one("""SELECT p.public_id FROM tpo.pagamenti_consegna p JOIN tpo.consegne c ON c.id=p.consegna_id
                     WHERE c.public_id=%s AND p.tipo='PAGAMENTO'
                       AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna a WHERE a.annulla_pagamento_id=p.id)""",
                  (con,))
    return row[0] if row else None


def fase_pagamento(b, ctx, con, metodo, pdf_dir: Path, appena_consegnata: bool):
    print("\n== PAGAMENTO ALLA CONSEGNA (10/10)")
    attivo = pagamento_attivo(ctx, con)
    if attivo:
        print(f"  consegna gia' pagata ({attivo}): salto.")
        return attivo
    if metodo is None:
        modello = (f".venv/bin/python scripts/commissioning/2026-10-11_pagamenti_consegne.py --pagata "
                   f"{con or 'CON-xxxxxx'} --metodo CONTANTI --data {GIORNO.isoformat()} --esegui")
        print("  metodo di pagamento NON indicato: non lo invento. Quando lo sai, lancia (cambia il metodo se serve):")
        print(f"    {modello}")
        print("  oppure rilancia questo script con --metodo BONIFICO|CONTANTI|CARTA|BIZUM|ALTRO --esegui.")
        return None
    key = f"{TAG}-pagamento-clandestino"
    nota = "Pagata alla consegna del 10/10/2026 (dichiarato da Matteo l'11/10/2026)"
    ctx.tpo(["pagamento-consegna", "registra", "--consegna", con or "CON-??????", "--data", GIORNO.isoformat(),
             "--metodo", metodo, "--note", nota, "--actor", b.ACTOR, "--reason",
             "Pagamento alla consegna a Clandestino dichiarato da Matteo", "--correlation-id", key,
             "--idempotency-key", key], f"pagamento consegna {con or '(anteprima)'} ({metodo})")
    if con and ctx.execute:
        pdf_dir.mkdir(parents=True, exist_ok=True)
        ctx.tpo(["bolla", "genera", "--consegna", con, "--output-dir", str(pdf_dir), "--per-cliente",
                 "--sovrascrivi"], f"bolla PDF {con} (rigenerata con 'pagado')")
    return pagamento_attivo(ctx, con) if ctx.execute else None


# --------------------------------------------------------------------------------------------- programma
def fase_programma(b, ctx, cid_esistente: bool, saltare: bool, conn):
    print(f"\n== PROGRAMMA RICORRENTE: ogni giovedi' dal {PROGRAMMA_PRIMA} ({', '.join(PROGRAMMA_RIGHE)} SET)")
    if saltare:
        print("  saltato (--senza-programma).")
        return
    if not cid_esistente and not ctx.execute:
        print(f"  (anteprima) {CLIENTE} non esiste ancora: verra' creato un programma OGNI_X_GIORNI "
              f"{PROGRAMMA_OGNI_GIORNI} giorni, prima consegna {PROGRAMMA_PRIMA}, riga "
              + ", ".join(PROGRAMMA_RIGHE) + ".")
        return
    esiste = ctx.one("""SELECT pf.public_id FROM tpo.programmi_fornitura pf
                        JOIN tpo.programmi_fornitura_versioni v ON v.programma_fornitura_id=pf.id
                        JOIN tpo.clienti c ON c.id=pf.cliente_id
                        WHERE c.denominazione=%s AND v.valida_al IS NULL AND v.stato='ATTIVO'""", (CLIENTE,))
    if esiste:
        print(f"  {CLIENTE} ha gia' il programma ATTIVO {esiste[0]}: salto.")
        return
    p = carica_programma()
    rc = p.run(conn, CLIENTE, PROGRAMMA_RIGHE, PROGRAMMA_PRIMA, PROGRAMMA_OGNI_GIORNI,
               "Clandestino ricorrente: ogni giovedi' 1 SET di Cilantro fisso; altre due mezze varieta' da "
               "aggiungere in seguito", ctx.execute)
    if rc != 0:
        raise b.Stop("il programma non e' stato creato (vedi sopra).")


# --------------------------------------------------------------------------------------------- correttivi
def correttivi(ctx, con):
    print("\n== COMANDI CORRETTIVI (copia solo se serve cambiare qualcosa)")
    pag = pagamento_attivo(ctx, con) if con else None
    if pag:
        print(f"  Pagamento {pag} registrato per errore (metodo/data sbagliati):")
        print(f"    .venv/bin/python {SELF.replace('2026-10-11_clandestino', '2026-10-11_pagamenti_consegne')} "
              f"--annulla {pag} --esegui")
        print(f"    poi: ... 2026-10-11_pagamenti_consegne.py --pagata {con} --metodo <METODO> "
              f"--data {GIORNO.isoformat()} --esegui")
    else:
        print("  Pagamento: nessuno registrato (annullabile con --annulla PGC-... dopo averlo registrato).")
    print("  Consegna, raccolte, cliente, programma: sono registrazioni di autorita' (consegna CONSEGNATA immutabile).")
    print("  Se qualcosa non torna (quantita', semina, orario) dimmelo e preparo la correzione governata.")


def run(ctx, orari: Orari, metodo, pdf_dir: Path, senza_programma: bool, conn=None) -> int:
    b = carica_base()
    ctx.check_head()
    conn = conn or ctx.conn
    esisteva = ctx.one("SELECT 1 FROM tpo.clienti WHERE denominazione=%s", (CLIENTE,)) is not None
    for varieta, qty, semina in VOCI:        # tutti i controlli PRIMA di scrivere qualsiasi cosa
        verifica_raccolta(b, ctx, orari, varieta, qty, semina, True)
    fase_pronta(b, ctx, orari)
    cid = fase_cliente(b, ctx)
    fase_raccolte(b, ctx, orari)
    con, _ = fase_consegna(b, ctx, cid, orari)
    if con is None and ctx.execute:
        raise b.Stop("consegna non registrata")
    fase_pagamento(b, ctx, con, metodo, pdf_dir, True)
    fase_programma(b, ctx, esisteva or ctx.execute, senza_programma, conn)
    correttivi(ctx, con)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metodo", choices=METODI, help="metodo con cui Clandestino ha pagato il 10/10 (non inventato)")
    ap.add_argument("--ora-pronta", default="09:50")
    ap.add_argument("--ora-raccolta", default="10:00")
    ap.add_argument("--ora-consegna", default="10:05")
    ap.add_argument("--senza-programma", action="store_true")
    ap.add_argument("--pdf-dir", default=str(PDF_DIR_DEFAULT))
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    b = carica_base()
    orari = Orari(a.ora_pronta, a.ora_raccolta, a.ora_consegna)
    ctx = b.Ctx(a.esegui, Path(a.pdf_dir))
    try:
        print(f"== CLANDESTINO -- {'ESECUZIONE' if a.esegui else 'ANTEPRIMA (nulla viene scritto)'}")
        run(ctx, orari, a.metodo, Path(a.pdf_dir), a.senza_programma)
        if not a.esegui:
            print("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        print("\n== FINE")
        return 0
    except b.Stop as exc:
        print(f"\nSTOP: {exc}", file=sys.stderr)
        return 1
    finally:
        ctx.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
