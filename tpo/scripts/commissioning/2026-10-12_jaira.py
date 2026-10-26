"""Consegna a LA JAIRA del 12/10/2026 (richiesta di Matteo): Afila 1 + Rabano 0.5 + Cilantro 0.5 SET.

In piu', dichiarazione di Matteo: l'Afila SEM-000021 (7 SET, in luce dal 9/10) "da oggi e' pronto alla raccolta".

Registra, in quest'ordine (ogni passo e' idempotente: se rilanci, salta cio' che e' gia' fatto):
  1. SEM-000021 Afila: LUCE -> CRESCITA (1 minuto dopo la luce, passaggio amministrativo) -> PRONTA_ALLA_RACCOLTA
     all'istante di adesso (orario non osservato: registrato alla conferma, come le altre dichiarazioni);
  2. le raccolte con carico a magazzino dei SOLI SET che escono oggi: Afila 1 (SEM-000021), Cilantro 0.5
     (SEM-000013, gia' PRONTA) e Rabano 0.5 (SEM-000015, gia' PRONTA). Cambiabili con --cilantro-da / --rabano-da;
  3. la consegna a La Jaira (CLI-000008) con la provenienza di ogni riga:
       - se La Jaira ha UN ordine aperto con tutte e tre le righe e residuo sufficiente (il programma PF-000008,
         Afila 1 + Cilantro 0.5 + Rabano 0.5 ogni 14 giorni, ha un ordine il 13/10), la consegna si lega a quello;
       - se ce n'e' piu' d'uno lo script si ferma e li elenca (scegli con --ordine ORD-...);
       - se non ce n'e' nessuno, o con --manuale, crea un ordine manuale di oggi;
  4. la bolla PDF in <pdf-dir>/<cliente>/ (default ~/Desktop/bolle);
  5. il pagamento SOLO se indichi --metodo (nessun metodo viene inventato): altrimenti la consegna resta "da pagare"
     e lo script ti lascia il comando pronto.

Orari: tutti derivati dall'istante di adesso (salvato al primo --esegui e riusato nei rilanci): pronta = adesso,
raccolte = +1 minuto, consegna = +2 minuti. Cambiabile con --effective-at (ISO 8601, solo la pronta).

Sempre in ANTEPRIMA finche' non aggiungi --esegui. Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-12_jaira.py                 # anteprima
  .venv/bin/python scripts/commissioning/2026-10-12_jaira.py --esegui
  opzioni: --metodo CONTANTI|BONIFICO|CARTA|BIZUM|ALTRO   --ordine ORD-...   --manuale
           --cilantro-da SEM-...   --rabano-da SEM-...   --pdf-dir CARTELLA

Si ferma (senza scrivere altro) se: la migrazione non e' 20261020_0039; SEM-000021 non e' un'Afila da 7 SET in
LUCE/CRESCITA/PRONTA; una semina non e' PRONTA_ALLA_RACCOLTA; una raccolta supera i SET attesi; la giacenza di una
varieta' non e' 0 prima del carico; gli ordini aperti di La Jaira sono ambigui.

COMANDI CORRETTIVI (stampati anche a fine esecuzione con gli id esatti):
  pagamento sbagliato (metodo/data):  .venv/bin/python scripts/commissioning/2026-10-11_pagamenti_consegne.py --annulla PGC-... --esegui
                                      poi: ... --pagata CON-... --metodo M --data 2026-10-12 --esegui
  consegna / raccolte / transizioni:  registrazioni di autorita' (consegna CONSEGNATA immutabile): se qualcosa non
                                      torna dimmelo e preparo la correzione governata.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

BASE_SCRIPT = ROOT / "scripts" / "commissioning" / "2026-10-08_consegne_giornata.py"
TAG = "jaira-2026-10-12"
HEAD = "20261020_0039"
GIORNO = date(2026, 10, 12)
WORK = ROOT / "outputs" / "jaira_2026_10_12"
METODI = ("BONIFICO", "CONTANTI", "CARTA", "BIZUM", "ALTRO")
SELF = "scripts/commissioning/2026-10-12_jaira.py"

# cliente per id pubblico + frammento di nome atteso (a sistema potrebbe chiamarsi "La Jaira")
JAIRA = ("CLI-000008", "Jaira")
# (semina, varieta, SET attesi a sistema = SET dichiarati pronti da Matteo)
PRONTA = ("SEM-000021", "Afila", "7")
# (varieta, SET, semina di provenienza)
VOCI = [("Afila", "1", "SEM-000021"), ("Cilantro", "0.5", "SEM-000013"), ("Rabano", "0.5", "SEM-000015")]

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


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


class Orari:
    """pronta = base, raccolte = +1 minuto, consegna = +2 minuti (la base e' l'istante di adesso)."""

    def __init__(self, base: datetime) -> None:
        self.pronta = base
        self.raccolta = base + timedelta(minutes=1)
        self.consegna = base + timedelta(minutes=2)


# --------------------------------------------------------------------------------------------- cliente
def controlla_cliente(b, ctx) -> str:
    row = ctx.one("SELECT denominazione FROM tpo.clienti WHERE public_id=%s", (JAIRA[0],))
    if not row or b._fold(JAIRA[1]) not in b._fold(row[0]):
        raise b.Stop(f"cliente {JAIRA[0]}: a sistema {row and row[0]!r}, atteso un nome con {JAIRA[1]!r}. Non procedo.")
    print(f"== CLIENTE {JAIRA[0]} = {row[0]}")
    return JAIRA[0]


# --------------------------------------------------------------------------------------------- pronta
def fase_pronta(b, ctx, orari: Orari):
    semina, varieta, dichiarati = PRONTA
    print(f"\n== {varieta.upper()} {semina}: dichiarazione di Matteo 'pronto alla raccolta da oggi' "
          f"(istante {orari.pronta:%d/%m %H:%M})")
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
                  f"dichiarata da Matteo il 12/10/2026 ({varieta} {dichiarati} SET pronti da oggi); "
                  "orario non osservato, registrato alla conferma"))
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


def fase_raccolte(b, ctx, orari: Orari, voci):
    print("\n== RACCOLTE E CARICHI A MAGAZZINO (solo i SET che escono oggi)")
    for varieta, qty, semina in voci:
        done, codice, attesi, raccolti, giac = verifica_raccolta(b, ctx, orari, varieta, qty, semina, not ctx.execute)
        print(f"\n{varieta}: {qty} SET da {semina} ({codice}); giacenza {_n(giac)}; gia' raccolti {_n(raccolti)} "
              f"su {_n(attesi) if attesi is not None else '?'}" + ("  [raccolta gia' registrata]" if done else ""))
        note = f"Raccolta {varieta} {qty} SET ({semina}) per la consegna a La Jaira del 12/10/2026, dichiarata da Matteo"
        out = ctx.tpo(["raccolta", "record", "--semina", semina, "--quantity", qty, "--uom", "SET",
                       "--effective-at", orari.raccolta.isoformat(), "--notes", note, "--actor", b.ACTOR,
                       "--reason", note, "--correlation-id", f"{TAG}-raccolta-{semina}",
                       "--idempotency-key", f"{TAG}-raccolta-{semina}", "--confirm"], f"raccolta {varieta}")
        racc = b.kv(out, "RACCOLTA_ID") or done or "RAC-??????(da anteprima)"
        motivo = f"Carico magazzino da raccolta {varieta} {qty} SET ({semina}), consegna La Jaira 12/10"
        ctx.tpo(["movimento", "carica-raccolta", "--raccolta", racc, "--unita-misura", "SET", "--effective-at",
                 orari.raccolta.isoformat(), "--motivo", motivo, "--actor", b.ACTOR, "--reason", motivo,
                 "--correlation-id", f"{TAG}-carico-{semina}", "--idempotency-key", f"{TAG}-carico-{semina}",
                 "--confirm"], f"carico {racc} ({varieta})")


# --------------------------------------------------------------------------------------------- ordine
def trova_ordine(b, ctx, cid, voci, ordine_forzato, manuale):
    """Ritorna (ordine, {varieta_id: riga}, data_prevista) di un ordine aperto che copre tutte le voci,
    oppure None per un ordine manuale. Si ferma se i candidati sono piu' d'uno."""
    print("\n== ORDINI APERTI DI LA JAIRA (per le tre varieta')")
    per_ordine: dict[str, dict] = {}
    for nome, qty, _ in voci:
        vid = b.varieta_id(ctx, nome)
        rows = b.righe_aperte(ctx, cid, vid)
        if not rows:
            print(f"  {nome}: nessuna riga aperta")
        for ordine, riga, data, quantita, residuo in rows:
            ok = Decimal(residuo) >= Decimal(qty)
            print(f"  {ordine} {riga} {nome}: prevista {data}, quantita' {_n(quantita)}, residuo {_n(residuo)} SET"
                  + ("" if ok else f"  (residuo < {qty}: non copre)"))
            if ok:
                entry = per_ordine.setdefault(ordine, {"righe": {}, "data": data})
                entry["righe"][vid] = riga
    complete = {o: e for o, e in per_ordine.items() if len(e["righe"]) == len(voci)}
    if ordine_forzato:
        if ordine_forzato not in complete:
            raise b.Stop(f"{ordine_forzato} non e' un ordine aperto di La Jaira con tutte e tre le righe e residuo "
                         "sufficiente.")
        complete = {ordine_forzato: complete[ordine_forzato]}
    if manuale:
        print("  --manuale: creo un ordine manuale di oggi (gli ordini aperti sopra restano come sono).")
        return None
    if len(complete) > 1:
        raise b.Stop("piu' ordini aperti di La Jaira coprono le tre righe: " + ", ".join(sorted(complete))
                     + ". Rilancia con --ordine ORD-... (quello da evadere) oppure --manuale.")
    if not complete:
        print("  nessun ordine aperto copre Afila + Cilantro + Rabano: creo un ordine manuale di oggi.")
        return None
    ordine, e = next(iter(complete.items()))
    print(f"  -> la consegna si lega a {ordine} (prevista {e['data']})")
    return ordine, e["righe"], e["data"]


# --------------------------------------------------------------------------------------------- consegna
def fase_consegna(b, ctx, cid, orari: Orari, voci, ordine_forzato, manuale):
    print("\n== CONSEGNA a La Jaira")
    fatta = b.audit_fatto(ctx, "CONSEGNA", f"{TAG}-consegna-jaira")
    if fatta:
        print(f"  consegna gia' registrata ({fatta}): salto.")
        return fatta
    trovato = trova_ordine(b, ctx, cid, voci, ordine_forzato, manuale)
    testo = " + ".join(f"{v} {q} SET ({s})" for v, q, s in voci)
    reason = "Consegna a La Jaira del 12/10/2026: Afila 1, Cilantro 0.5, Rabano 0.5 SET"
    if trovato is None:
        ord_man, righe_man = b.ordine_manuale(
            ctx, cid, voci, "jaira",
            "Vendita a La Jaira del 12/10/2026: Afila 1 + Cilantro 0.5 + Rabano 0.5 SET (stesse quantita' del "
            "programma PF-000008)")
        if ord_man is None:
            print(f"  (anteprima) consegna: {testo} su nuovo ordine manuale")
            return None
        ordine, righe_o, planned = ord_man, righe_man, GIORNO.isoformat()
    else:
        ordine, righe_o, data = trovato
        planned = min(str(data), GIORNO.isoformat())
        if not ctx.execute:
            print(f"  (anteprima) consegna: {testo} su {ordine}, data prevista registrata {planned}")
            return None
    righe = b.righe_consegna(ctx, ordine, righe_o, voci)
    con = b.consegna(ctx, cid, planned, orari.consegna.isoformat(), righe, "jaira", reason)
    b.bolla(ctx, con)
    return con


# --------------------------------------------------------------------------------------------- pagamento
def pagamento_attivo(ctx, con):
    if con is None:
        return None
    row = ctx.one("""SELECT p.public_id FROM tpo.pagamenti_consegna p JOIN tpo.consegne c ON c.id=p.consegna_id
                     WHERE c.public_id=%s AND p.tipo='PAGAMENTO'
                       AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna a WHERE a.annulla_pagamento_id=p.id)""",
                  (con,))
    return row[0] if row else None


def fase_pagamento(b, ctx, con, metodo, pdf_dir: Path):
    print("\n== PAGAMENTO ALLA CONSEGNA")
    attivo = pagamento_attivo(ctx, con)
    if attivo:
        print(f"  consegna gia' pagata ({attivo}): salto.")
        return attivo
    if metodo is None:
        print("  metodo NON indicato: la consegna resta 'da pagare' (non invento nulla). Quando La Jaira paga:")
        print(f"    .venv/bin/python scripts/commissioning/2026-10-11_pagamenti_consegne.py --pagata "
              f"{con or 'CON-xxxxxx'} --metodo CONTANTI --data {GIORNO.isoformat()} --esegui")
        print("  oppure rilancia questo script con --metodo BONIFICO|CONTANTI|CARTA|BIZUM|ALTRO --esegui.")
        return None
    key = f"{TAG}-pagamento-jaira"
    ctx.tpo(["pagamento-consegna", "registra", "--consegna", con or "CON-??????", "--data", GIORNO.isoformat(),
             "--metodo", metodo, "--note", "Pagata alla consegna del 12/10/2026 (dichiarato da Matteo)",
             "--actor", b.ACTOR, "--reason", "Pagamento alla consegna a La Jaira dichiarato da Matteo",
             "--correlation-id", key, "--idempotency-key", key], f"pagamento consegna {con or '(anteprima)'} ({metodo})")
    if con and ctx.execute:
        pdf_dir.mkdir(parents=True, exist_ok=True)
        ctx.tpo(["bolla", "genera", "--consegna", con, "--output-dir", str(pdf_dir), "--per-cliente",
                 "--sovrascrivi"], f"bolla PDF {con} (rigenerata con 'pagado')")
    return pagamento_attivo(ctx, con) if ctx.execute else None


# --------------------------------------------------------------------------------------------- correttivi
def correttivi(ctx, con):
    print("\n== COMANDI CORRETTIVI (copia solo se serve cambiare qualcosa)")
    pag = pagamento_attivo(ctx, con) if con else None
    if pag:
        print(f"  Pagamento {pag} registrato per errore (metodo/data sbagliati):")
        print(f"    .venv/bin/python scripts/commissioning/2026-10-11_pagamenti_consegne.py --annulla {pag} --esegui")
        print(f"    poi: ... 2026-10-11_pagamenti_consegne.py --pagata {con} --metodo <METODO> "
              f"--data {GIORNO.isoformat()} --esegui")
    else:
        print("  Pagamento: nessuno registrato (annullabile con --annulla PGC-... dopo averlo registrato).")
    print("  Consegna, raccolte, transizioni: registrazioni di autorita' (consegna CONSEGNATA immutabile).")
    print("  Se qualcosa non torna (quantita', semina, orario) dimmelo e preparo la correzione governata.")


def run(ctx, orari: Orari, voci, metodo, pdf_dir: Path, ordine_forzato=None, manuale=False) -> int:
    b = carica_base()
    ctx.check_head()
    cid = controlla_cliente(b, ctx)
    for varieta, qty, semina in voci:        # tutti i controlli PRIMA di scrivere qualsiasi cosa
        verifica_raccolta(b, ctx, orari, varieta, qty, semina, True)
    if not b.audit_fatto(ctx, "CONSEGNA", f"{TAG}-consegna-jaira"):
        trova_ordine(b, ctx, cid, voci, ordine_forzato, manuale)       # ambiguita' = stop prima di scrivere
    fase_pronta(b, ctx, orari)
    fase_raccolte(b, ctx, orari, voci)
    con = fase_consegna(b, ctx, cid, orari, voci, ordine_forzato, manuale)
    if con is None and ctx.execute:
        raise b.Stop("consegna non registrata")
    fase_pagamento(b, ctx, con, metodo, pdf_dir)
    correttivi(ctx, con)
    return 0


def voci_con_override(cilantro_da, rabano_da):
    out = []
    for varieta, qty, semina in VOCI:
        if varieta == "Cilantro" and cilantro_da:
            semina = cilantro_da
        if varieta == "Rabano" and rabano_da:
            semina = rabano_da
        out.append((varieta, qty, semina))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metodo", choices=METODI, help="metodo con cui La Jaira ha pagato oggi (non inventato)")
    ap.add_argument("--ordine", help="ordine aperto di La Jaira da evadere (se ce n'e' piu' d'uno)")
    ap.add_argument("--manuale", action="store_true", help="non legare a un ordine aperto: crea un ordine manuale")
    ap.add_argument("--cilantro-da", metavar="SEM-...", help="semina del Cilantro (default SEM-000013)")
    ap.add_argument("--rabano-da", metavar="SEM-...", help="semina del Rabano (default SEM-000015)")
    ap.add_argument("--effective-at", help="istante ISO 8601 della pronta (default: adesso, salvato al primo --esegui)")
    ap.add_argument("--pdf-dir", default=str(Path.home() / "Desktop" / "bolle"))
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    b = carica_base()
    base = b.instant("pronta", a.esegui, a.effective_at)
    orari = Orari(base)
    ctx = b.Ctx(a.esegui, Path(a.pdf_dir))
    try:
        print(f"== LA JAIRA 12/10/2026 -- {'ESECUZIONE' if a.esegui else 'ANTEPRIMA (nulla viene scritto)'} "
              f"(istante {base:%Y-%m-%d %H:%M})")
        run(ctx, orari, voci_con_override(a.cilantro_da, a.rabano_da), a.metodo, Path(a.pdf_dir), a.ordine,
            a.manuale)
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
