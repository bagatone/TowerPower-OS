"""CONSEGNA A UN CLIENTE - comando unico (12/10/2026): indichi cliente e cosa consegni, il resto lo fa lui.

  .venv/bin/python scripts/commissioning/2026-10-12_consegna.py "La Jaira" Afila:1 Cilantro:0.5 Rabano:0.5
  ... --esegui                      per scrivere davvero (senza: solo ANTEPRIMA, non scrive nulla)

Ogni voce e' Varieta:SET oppure Varieta:SET:SEM-000021 (semina di provenienza esplicita). Se la semina non c'e', il
comando PROPONE la semina PRONTA_ALLA_RACCOLTA piu' vecchia con abbastanza SET ancora da raccogliere (o dichiarata
pronta con --pronta) e la mostra nell'anteprima, con le alternative: tu confermi lanciando --esegui; per cambiarla la
scrivi tu. Se non c'e' nessuna semina adatta si ferma e ti elenca le semine di quella varieta'.

Cosa registra, in quest'ordine (tutto idempotente: se rilanci salta cio' che e' gia' fatto):
  1. (solo con --nuovo-cliente) il cliente, senza dati fiscali. Si ferma se esiste un nome simile (es. Salvaje/Selvaje)
     a meno di --anche-se-simile; senza --nuovo-cliente un cliente sconosciuto e' un errore, non una creazione;
  2. (solo con --pronta SEM-...:SET) la dichiarazione "pronto alla raccolta" (anche da GERMINAZIONE: LUCE +1 minuto): LUCE -> CRESCITA (+1 minuto) ->
     PRONTA_ALLA_RACCOLTA; i SET dichiarati devono coincidere con i SET attesi a sistema, altrimenti si ferma;
  3. le raccolte con carico a magazzino dei SOLI SET che escono (salvo --da-giacenza Varieta': esce dalla giacenza,
     nessuna raccolta);
  4. la consegna: legata all'ordine aperto del cliente se UNO SOLO copre tutte le voci con data entro
     --finestra-giorni (default 3) dal giorno della consegna; altrimenti ordine manuale. --ordine ORD-... lega le
     voci coperte da quell'ordine (le altre vanno su un ordine manuale); ripetibile (--ordine ORD-A --ordine ORD-B:
     ogni voce va sul primo ordine elencato che la copre); --manuale non lega a nulla;
  5. la bolla PDF in <pdf-dir>/<cliente>/ (default ~/Desktop/bolle);
  6. il pagamento SOLO con --metodo (nessun metodo e' inventato): senza, la consegna resta "da pagare" e il comando
     per registrarlo viene stampato;
  7. (solo con --programma-riga ...) il programma ricorrente del cliente.

DATA E ORA: di default adesso. Per registrare un giorno passato: --giorno AAAA-MM-GG --ora HH:MM (obbligatoria; e' l'ora
della dichiarazione "pronta" o, se non c'e', delle raccolte; poi raccolte +1 minuto, consegna +2). Gli orari non
osservati vengono scritti come tali nei motivi registrati. Il piano (istante e semine scelte) si salva alla prima
esecuzione in outputs/consegna/ e i rilanci lo riusano.

Stesso cliente, stesso giorno, stesse varieta'/quantita' = la stessa consegna (rilancio idempotente). Per una SECONDA
consegna identica nello stesso giorno aggiungi --replica 2.

Opzioni: --metodo BONIFICO|CONTANTI|CARTA|BIZUM|ALTRO  --pronta SEM-...:SET (ripetibile)  --da-giacenza Varieta'
         --oltre-attesi (raccolte oltre i SET attesi: sono una stima, la quantita' fisica la dichiari tu)
         --nuovo-cliente [--anche-se-simile]   --programma-riga Var:SET (ripetibile) --programma-prima AAAA-MM-GG
         --programma-ogni N (default 14)   --pdf-dir CARTELLA

Si ferma (senza scrivere altro) se: la migrazione non e' 20261010_0038; una varieta' e' ripetuta; una semina non e'
PRONTA_ALLA_RACCOLTA (e non dichiarata con --pronta); una raccolta supera i SET attesi; la giacenza di una varieta'
non e' 0 prima del carico; la giacenza non basta (--da-giacenza); la consegna di un giorno passato non ha --ora.

COMANDI CORRETTIVI: stampati a fine esecuzione con gli id esatti (pagamento sbagliato: --annulla PGC-...). Consegna,
raccolte e transizioni sono registrazioni di autorita' (consegna CONSEGNATA immutabile): se qualcosa non torna dimmelo.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import json
import re
import sys
import unicodedata
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

BASE_SCRIPT = ROOT / "scripts" / "commissioning" / "2026-10-08_consegne_giornata.py"
PROGRAMMA_SCRIPT = ROOT / "scripts" / "commissioning" / "2026-10-08_nuovo_programma.py"
HEAD = "20261010_0038"
LOCAL_TZ = ZoneInfo("Atlantic/Canary")
METODI = ("BONIFICO", "CONTANTI", "CARTA", "BIZUM", "ALTRO")
WORK = ROOT / "outputs" / "consegna"
PAGAMENTI = "scripts/commissioning/2026-10-11_pagamenti_consegne.py"

_BASE = None


def carica_base():
    global _BASE
    if _BASE is None:
        spec = importlib.util.spec_from_file_location("consegne_giornata_base", BASE_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        module.HEAD = HEAD
        _BASE = module
    return _BASE


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


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _fold(text)).strip("-") or "cliente"


# --------------------------------------------------------------------------------------------- richiesta
class Richiesta:
    """Tutto cio' che Matteo ha chiesto, validato; non tocca il database."""

    def __init__(self, cliente, voci, *, giorno=None, ora=None, metodo=None, pronte=(), da_giacenza=(),
                 oltre_attesi=False, nuovo_cliente=False, anche_se_simile=False, ordine=None, manuale=False,
                 finestra_giorni=3, programma_righe=(), programma_prima=None, programma_ogni=14, replica=1,
                 pdf_dir=None, oggi=None, adesso=None):
        b = carica_base()
        self.cliente = cliente.strip()
        self.oggi = oggi or datetime.now(LOCAL_TZ).date()
        self.giorno = giorno or self.oggi
        self.ora = ora
        self.adesso = adesso
        self.metodo = metodo
        self.oltre_attesi = oltre_attesi
        self.nuovo_cliente = nuovo_cliente
        self.anche_se_simile = anche_se_simile
        self.ordini = [ordine] if isinstance(ordine, str) else list(ordine or [])
        self.ordine = self.ordini[0] if self.ordini else None
        self.manuale = manuale
        self.finestra_giorni = finestra_giorni
        self.programma_righe = list(programma_righe)
        self.programma_prima = programma_prima
        self.programma_ogni = programma_ogni
        self.replica = replica
        self.pdf_dir = Path(pdf_dir) if pdf_dir else Path.home() / "Desktop" / "bolle"
        self.voci = []                                  # (varieta', Decimal SET, semina|None)
        seen = set()
        for item in voci:
            parti = [p.strip() for p in item.split(":")]
            if len(parti) not in (2, 3) or not parti[0]:
                raise b.Stop(f"voce '{item}' non valida: usa Varieta:SET oppure Varieta:SET:SEM-000000.")
            try:
                qty = Decimal(parti[1].replace(",", "."))
            except InvalidOperation:
                raise b.Stop(f"quantita' non valida in '{item}'.") from None
            if qty <= 0 or (qty * 2) % 1 != 0:
                raise b.Stop(f"quantita' {parti[1]} in '{item}': i SET sono interi o mezzi (0.5, 1, 1.5, ...).")
            semina = parti[2].upper() if len(parti) == 3 else None
            if semina is not None and not re.fullmatch(r"SEM-\d{6}", semina):
                raise b.Stop(f"semina '{parti[2]}' in '{item}' non valida (formato SEM-000000).")
            if _fold(parti[0]) in seen:
                raise b.Stop(f"varieta' ripetuta: {parti[0]}. Una voce per varieta' (somma le quantita').")
            seen.add(_fold(parti[0]))
            self.voci.append((parti[0], qty, semina))
        if not self.voci:
            raise b.Stop("indica almeno una voce Varieta:SET.")
        self.pronte = []                                # (semina, Decimal SET dichiarati)
        for item in pronte:
            m = re.fullmatch(r"(SEM-\d{6}):([0-9]+(?:[.,][0-9]+)?)", item.strip().upper())
            if not m:
                raise b.Stop(f"--pronta '{item}' non valida: usa SEM-000000:SET (es. SEM-000021:7).")
            self.pronte.append((m.group(1), Decimal(m.group(2).replace(",", "."))))
        self.da_giacenza = {_fold(v) for v in da_giacenza}
        nomi = {_fold(v) for v, _, _ in self.voci}
        for g in self.da_giacenza:
            if g not in nomi:
                raise b.Stop(f"--da-giacenza {g}: non e' tra le voci della consegna.")
        if self.giorno > self.oggi:
            raise b.Stop(f"il giorno {self.giorno} e' nel futuro: la consegna si registra quando avviene.")
        if self.giorno != self.oggi and ora is None:
            raise b.Stop(f"consegna del {self.giorno} (non e' oggi): indica --ora HH:MM, l'ora (anche stimata) della "
                         "prima operazione; non uso 'adesso' per un giorno passato.")
        if self.programma_righe and (self.programma_prima is None):
            raise b.Stop("--programma-riga richiede --programma-prima AAAA-MM-GG.")
        if self.metodo and self.metodo not in METODI:
            raise b.Stop(f"metodo '{self.metodo}' sconosciuto ({', '.join(METODI)}).")

    @property
    def tag(self) -> str:
        chiave = json.dumps(sorted((_fold(v), _n(q)) for v, q, _ in self.voci))
        sigla = hashlib.sha256(chiave.encode()).hexdigest()[:6]
        base = f"consegna-{self.giorno.isoformat()}-{_slug(self.cliente)}-{sigla}"
        return base if self.replica == 1 else f"{base}-r{self.replica}"


class Orari:
    def __init__(self, base: datetime) -> None:
        self.pronta = base
        self.raccolta = base + timedelta(minutes=1)
        self.consegna = base + timedelta(minutes=2)


def calcola_base(req: Richiesta, esegui: bool) -> datetime:
    """Istante base: --ora, oppure quello salvato alla prima esecuzione, oppure adesso (minuto intero)."""
    if req.ora:
        ore, minuti = (int(x) for x in req.ora.split(":"))
        return datetime.combine(req.giorno, time(ore, minuti), tzinfo=LOCAL_TZ)
    path = WORK / f"piano_{req.tag}.json"
    if path.exists():
        salvato = json.loads(path.read_text()).get("base")
        if salvato:
            return datetime.fromisoformat(salvato)
    adesso = req.adesso or datetime.now(LOCAL_TZ).replace(second=0, microsecond=0)
    return adesso


def piano_path(req: Richiesta) -> Path:
    return WORK / f"piano_{req.tag}.json"


def piano_salvato(req: Richiesta) -> dict:
    path = piano_path(req)
    return json.loads(path.read_text()) if path.exists() else {}


def salva_piano(req: Richiesta, base: datetime, scelte: dict) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    piano_path(req).write_text(json.dumps({"base": base.isoformat(), "semine": scelte}, indent=2))


# --------------------------------------------------------------------------------------------- cliente
def risolvi_cliente(b, ctx, req: Richiesta):
    """Ritorna (public_id|None, denominazione, da_creare)."""
    rows = ctx.q("SELECT public_id, denominazione FROM tpo.clienti")
    print(f"== CLIENTE '{req.cliente}'")
    if re.fullmatch(r"CLI-\d{6}", req.cliente.upper()):
        trovati = [r for r in rows if r[0] == req.cliente.upper()]
        if not trovati:
            raise b.Stop(f"cliente {req.cliente} inesistente.")
        print(f"  {trovati[0][0]} = {trovati[0][1]}")
        return trovati[0][0], trovati[0][1], False
    f = _fold(req.cliente)
    esatti = [r for r in rows if _fold(r[1]) == f]
    if len(esatti) > 1:
        raise b.Stop(f"piu' clienti si chiamano '{req.cliente}': " + ", ".join(f"{r[0]} {r[1]}" for r in esatti)
                     + ". Indica l'id (CLI-000000).")
    if esatti:
        print(f"  {esatti[0][0]} = {esatti[0][1]}")
        return esatti[0][0], esatti[0][1], False
    contenuti = [r for r in rows if f and f in _fold(r[1])]
    if len(contenuti) == 1 and not req.nuovo_cliente:
        print(f"  interpreto come {contenuti[0][0]} = {contenuti[0][1]}")
        return contenuti[0][0], contenuti[0][1], False
    simili = list({r for r in rows if difflib.SequenceMatcher(None, _fold(r[1]), f).ratio() >= 0.75} | set(contenuti))
    elenco = ", ".join(f"{r[0]} {r[1]}" for r in sorted(simili))
    if not req.nuovo_cliente:
        raise b.Stop(f"cliente '{req.cliente}' non trovato" + (f" (simili: {elenco})" if elenco else "")
                     + ". Se e' un cliente NUOVO aggiungi --nuovo-cliente; altrimenti scrivi l'id (CLI-000000).")
    if simili and not req.anche_se_simile:
        raise b.Stop(f"esiste gia' un cliente dal nome simile: {elenco}. Se e' lo stesso usa quello (nome o id); se "
                     "e' davvero un altro cliente aggiungi --anche-se-simile.")
    print("  non esiste: verra' creato come cliente nuovo (senza dati fiscali).")
    return None, req.cliente, True


def crea_cliente(b, ctx, req: Richiesta) -> str:
    nxt = ctx.one("SELECT COALESCE(max(substring(public_id from 5)::int),0)+1 FROM tpo.clienti")[0]
    cid = f"CLI-{int(nxt):06d}"
    ctx.tpo(["onboarding", "customer", "--customer-id", cid, "--denomination", req.cliente, "--actor", b.ACTOR,
             "--reason", f"Nuovo cliente {req.cliente}, prima consegna il {req.giorno.strftime('%d/%m/%Y')}; "
                         "dati fiscali non ancora disponibili",
             "--correlation-id", f"{b.TAG}-cliente"], f"nuovo cliente {req.cliente} ({cid})")
    return cid


# --------------------------------------------------------------------------------------------- semine
def semine_candidate(ctx, nome_varieta, pronte):
    """Semine della varieta' che possono essere raccolte: PRONTA_ALLA_RACCOLTA o dichiarate pronte ora.
    [(semina, stato, codice, attesi, raccolti, residuo)], dalla piu' vecchia."""
    vid = carica_base().varieta_id(ctx, nome_varieta)
    dichiarate = {s for s, _ in pronte}
    rows = ctx.q("""SELECT s.public_id, s.stato::text, s.codice_tracciabilita, s.expected_useful_quantity,
                           s.expected_useful_uom::text,
                           COALESCE((SELECT SUM(r.quantita) FROM tpo.raccolte r
                                     WHERE r.semina_id=s.id AND r.unita_misura='SET'),0)
                    FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
                    WHERE v.public_id=%s ORDER BY s.data_avvio, s.id""", (vid,))
    out = []
    for sem, stato, codice, attesi, uom, raccolti in rows:
        if stato == "PRONTA_ALLA_RACCOLTA" or (sem in dichiarate and stato in ("GERMINAZIONE", "LUCE", "CRESCITA")):
            if attesi is None or uom != "SET":
                continue
            out.append((sem, stato, codice, Decimal(attesi), Decimal(raccolti), Decimal(attesi) - Decimal(raccolti)))
    return out


def scegli_semine(b, ctx, req: Richiesta, salvate: dict):
    """{varieta': semina|None} per ogni voce (None = da giacenza senza semina esplicita). Stampa le scelte."""
    print("\n== SEMINE DI PROVENIENZA")
    scelte, usati = {}, {}
    for nome, qty, esplicita in req.voci:
        giac = _fold(nome) in req.da_giacenza
        if giac:
            scelte[nome] = esplicita
            print(f"  {nome} {_n(qty)}: dalla GIACENZA" + (f" (provenienza {esplicita})" if esplicita else "")
                  + ", nessuna raccolta")
            continue
        if esplicita:
            scelte[nome] = esplicita
            print(f"  {nome} {_n(qty)}: {esplicita} (indicata da te)")
            continue
        if nome in salvate and salvate[nome]:
            scelte[nome] = salvate[nome]
            print(f"  {nome} {_n(qty)}: {salvate[nome]} (dal piano salvato alla prima esecuzione)")
            continue
        cand = semine_candidate(ctx, nome, req.pronte)
        ok = [c for c in cand if c[5] >= qty + usati.get(c[0], Decimal(0))]
        if not ok:
            righe = "\n".join(f"      {c[0]} {c[2]} {c[1]}: attesi {_n(c[3])}, raccolti {_n(c[4])}, residuo {_n(c[5])}"
                              for c in cand) or "      nessuna semina pronta"
            raise b.Stop(f"{nome}: nessuna semina PRONTA_ALLA_RACCOLTA con almeno {_n(qty)} SET ancora da raccogliere.\n"
                         f"{righe}\n  Se una semina e' pronta ma il sistema non lo sa: --pronta SEM-000000:SET. "
                         "Se ne indichi una tu, scrivila come Varieta:SET:SEM-000000 (con --oltre-attesi se i SET "
                         "fisici superano gli attesi).")
        scelta = ok[0]
        scelte[nome] = scelta[0]
        usati[scelta[0]] = usati.get(scelta[0], Decimal(0)) + qty
        altre = [c for c in ok[1:]]
        print(f"  {nome} {_n(qty)}: {scelta[0]} ({scelta[2]}, {scelta[1]}, residuo {_n(scelta[5])}) PROPOSTA"
              + (f"; alternative: {', '.join(f'{c[0]} (residuo {_n(c[5])})' for c in altre)}" if altre else ""))
    return scelte


# --------------------------------------------------------------------------------------------- pronta
def piano_pronta(b, ctx, orari: Orari, semina, dichiarati):
    """Controlla e costruisce le transizioni; non scrive. Ritorna (version, [(stato, istante, nota)]) o None."""
    stato, version, attesi, uom, varieta, codice, raccolti = b.semina_row(ctx, semina, _nome_semina(ctx, semina))
    print(f"\n== {varieta.upper()} {semina} ({codice}): dichiarata 'pronta alla raccolta' ({_n(dichiarati)} SET), "
          f"istante {orari.pronta:%d/%m %H:%M}")
    print(f"  stato {stato}, attesi {_n(attesi) if attesi is not None else '?'} {uom or ''}, gia' raccolti {_n(raccolti)}")
    if stato == "PRONTA_ALLA_RACCOLTA":
        print("  gia' PRONTA_ALLA_RACCOLTA: nulla da fare")
        return None
    if attesi is None or uom != "SET" or Decimal(attesi) != Decimal(dichiarati):
        raise b.Stop(f"{semina}: i SET attesi a sistema ({_n(attesi) if attesi is not None else '?'}) non coincidono "
                     f"con i {_n(dichiarati)} SET dichiarati. Non scelgo io: dimmi quale semina e' pronta.")
    if stato not in ("GERMINAZIONE", "LUCE", "CRESCITA"):
        raise b.Stop(f"{semina} e' {stato}: la dichiarazione parte da GERMINAZIONE, LUCE o CRESCITA.")
    ultimo = b.ultimo_evento(ctx, semina)
    if ultimo is None:
        raise b.Stop(f"{semina}: nessun evento di ciclo di vita, non posso datare le transizioni.")
    steps = []
    ultimo_evento = ultimo
    if stato == "GERMINAZIONE":
        steps.append(("LUCE", ultimo + timedelta(minutes=1),
                      "passaggio amministrativo 1 minuto dopo la germinazione (data non osservata: semina registrata "
                      "in ritardo, gia' pronta alla dichiarazione)"))
        ultimo = steps[-1][1]
        stato = "LUCE"
    if stato == "LUCE":
        steps.append(("CRESCITA", ultimo + timedelta(minutes=1),
                      "passaggio amministrativo 1 minuto dopo la luce (LUCE e CRESCITA sono lo stesso processo)"))
    steps.append(("PRONTA_ALLA_RACCOLTA", orari.pronta,
                  f"dichiarata da Matteo ({varieta} {_n(dichiarati)} SET pronti); orario non osservato, "
                  "registrato alla conferma" if not _stimato(orari) else
                  f"dichiarata da Matteo ({varieta} {_n(dichiarati)} SET pronti); orario stimato, non osservato"))
    previous = ultimo_evento
    for nome, when, _ in steps:
        if when <= previous:
            raise b.Stop(f"{semina}: {nome} {when:%Y-%m-%d %H:%M} non e' dopo l'ultimo evento "
                         f"{previous:%Y-%m-%d %H:%M}.")
        previous = when
    for nome, when, _ in steps:
        print(f"  -> {nome} {when:%d/%m %H:%M}")
    return version, steps


_STIMATO = {"v": False}


def _stimato(orari) -> bool:
    return _STIMATO["v"]


def _nome_semina(ctx, semina) -> str:
    row = ctx.one("SELECT v.denominazione FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id "
                  "WHERE s.public_id=%s", (semina,))
    if not row:
        raise carica_base().Stop(f"semina {semina} inesistente")
    return row[0]


def applica_pronta(b, ctx, semina, version, steps):
    for nome, when, nota in steps:
        reason = f"Transizione {nome} {semina} del {when:%d/%m/%Y %H:%M}: {nota}"
        ctx.tpo(["semina", "transition", "--semina", semina, "--expected-semina-version", str(version),
                 "--target-state", nome, "--effective-at", when.isoformat(), "--provenance", b.PROV_TRANS,
                 "--actor", b.ACTOR, "--reason", reason,
                 "--correlation-id", f"{b.TAG}-lifecycle-{semina}-{nome}",
                 "--idempotency-key", f"{b.TAG}-lifecycle-{semina}-{nome}", "--confirm"], f"{semina} -> {nome}")
        version += 1


# --------------------------------------------------------------------------------------------- raccolte
def verifica_raccolta(b, ctx, req: Richiesta, orari: Orari, varieta, qty, semina, dichiarate):
    """Controlli di una raccolta; non scrive. Ritorna (done, codice, attesi, raccolti, giacenza)."""
    stato, _, attesi, uom, _, codice, raccolti = b.semina_row(ctx, semina, varieta)
    done = b.audit_fatto(ctx, "RACCOLTA", f"{b.TAG}-raccolta-{semina}")
    sara_pronta = semina in dichiarate and stato in ("GERMINAZIONE", "LUCE", "CRESCITA")
    if not done and stato != "PRONTA_ALLA_RACCOLTA" and not sara_pronta:
        raise b.Stop(f"{semina} ({varieta}) e' {stato}, non PRONTA_ALLA_RACCOLTA: se e' pronta dichiaralo con "
                     f"--pronta {semina}:SET.")
    ultimo = b.ultimo_evento(ctx, semina)
    if not done and not sara_pronta and ultimo is not None and orari.raccolta <= ultimo:
        raise b.Stop(f"{semina}: la raccolta ({orari.raccolta:%d/%m %H:%M}) non e' dopo l'ultimo evento "
                     f"({ultimo:%Y-%m-%d %H:%M}).")
    giac = b.giacenza_set(ctx, b.varieta_id(ctx, varieta))
    if not done and giac != 0:
        raise b.Stop(f"{varieta}: giacenza {_n(giac)} SET diversa da 0 prima del carico: dimmi come procedere "
                     "(oppure consegna dalla giacenza con --da-giacenza).")
    if not done and attesi is not None and Decimal(raccolti) + Decimal(qty) > Decimal(attesi) \
            and not req.oltre_attesi:
        raise b.Stop(f"{semina}: {_n(raccolti)} gia' raccolti + {_n(qty)} superano i {_n(attesi)} SET attesi. Se hai "
                     "davvero quei SET fisici (gli attesi sono una stima) rilancia con --oltre-attesi.")
    return done, codice, attesi, raccolti, giac


def fase_raccolte(b, ctx, req: Richiesta, orari: Orari, scelte, dichiarate):
    print(f"\n== RACCOLTE E CARICHI A MAGAZZINO (solo i SET che escono, {orari.raccolta:%d/%m %H:%M})")
    giorno = req.giorno.strftime("%d/%m/%Y")
    for varieta, qty, _ in req.voci:
        if _fold(varieta) in req.da_giacenza:
            giac = b.giacenza_set(ctx, b.varieta_id(ctx, varieta))
            print(f"\n{varieta}: {_n(qty)} SET dalla giacenza ({_n(giac)} SET a magazzino), nessuna raccolta")
            continue
        semina = scelte[varieta]
        done, codice, attesi, raccolti, giac = verifica_raccolta(b, ctx, req, orari, varieta, qty, semina, dichiarate)
        oltre = attesi is not None and Decimal(raccolti) + qty > Decimal(attesi)
        print(f"\n{varieta}: {_n(qty)} SET da {semina} ({codice}); giacenza {_n(giac)}; gia' raccolti {_n(raccolti)} "
              f"su {_n(attesi) if attesi is not None else '?'}" + ("  [raccolta gia' registrata]" if done else "")
              + ("  [OLTRE gli attesi: dichiarato da te]" if oltre and not done else ""))
        note = f"Raccolta {varieta} {_n(qty)} SET ({semina}) per la consegna a {req.cliente} del {giorno}, dichiarata da Matteo"
        if _stimato(orari):
            note += "; orario stimato"
        if oltre:
            note += f" (oltre i {_n(attesi)} SET attesi: quantita' fisica dichiarata dal titolare)"
        out = ctx.tpo(["raccolta", "record", "--semina", semina, "--quantity", _n(qty), "--uom", "SET",
                       "--effective-at", orari.raccolta.isoformat(), "--notes", note, "--actor", b.ACTOR,
                       "--reason", note, "--correlation-id", f"{b.TAG}-raccolta-{semina}",
                       "--idempotency-key", f"{b.TAG}-raccolta-{semina}", "--confirm"], f"raccolta {varieta}")
        racc = b.kv(out, "RACCOLTA_ID") or done or "RAC-??????(da anteprima)"
        motivo = f"Carico magazzino da raccolta {varieta} {_n(qty)} SET ({semina}), consegna {req.cliente} {giorno}"
        ctx.tpo(["movimento", "carica-raccolta", "--raccolta", racc, "--unita-misura", "SET", "--effective-at",
                 orari.raccolta.isoformat(), "--motivo", motivo, "--actor", b.ACTOR, "--reason", motivo,
                 "--correlation-id", f"{b.TAG}-carico-{semina}", "--idempotency-key", f"{b.TAG}-carico-{semina}",
                 "--confirm"], f"carico {racc} ({varieta})")


def controlla_giacenze(b, ctx, req: Richiesta):
    for varieta, qty, _ in req.voci:
        if _fold(varieta) in req.da_giacenza:
            giac = b.giacenza_set(ctx, b.varieta_id(ctx, varieta))
            if giac < qty:
                raise b.Stop(f"{varieta}: giacenza {_n(giac)} SET < {_n(qty)} richiesti con --da-giacenza.")


# --------------------------------------------------------------------------------------------- ordine
def trova_ordine(b, ctx, cid, req: Richiesta):
    """Ritorna [(ordine, {varieta_id: riga}, data, voci_coperte), ...] oppure None (= tutto su ordine manuale)."""
    print("\n== ORDINI APERTI DEL CLIENTE (per le varieta' consegnate)")
    per_ordine: dict[str, dict] = {}
    for nome, qty, _ in req.voci:
        vid = b.varieta_id(ctx, nome)
        rows = b.righe_aperte(ctx, cid, vid)
        if not rows:
            print(f"  {nome}: nessuna riga aperta")
        for ordine, riga, data, quantita, residuo in rows:
            suff = Decimal(residuo) >= qty
            vicino = abs((data - req.giorno).days) <= req.finestra_giorni if data else False
            note = []
            if not suff:
                note.append(f"residuo < {_n(qty)}: non copre")
            if not vicino:
                note.append(f"data lontana piu' di {req.finestra_giorni} giorni dalla consegna")
            elif suff and Decimal(residuo) > qty:
                note.append(f"dopo la consegna restano aperti {_n(Decimal(residuo) - qty)} SET")
            print(f"  {ordine} {riga} {nome}: prevista {data}, quantita' {_n(quantita)}, residuo {_n(residuo)} SET"
                  + (f"  ({'; '.join(note)})" if note else ""))
            if suff:
                entry = per_ordine.setdefault(ordine, {"righe": {}, "data": data, "voci": []})
                entry["righe"][vid] = riga
                entry["voci"].append(nome)
    if req.manuale:
        print("  --manuale: ordine manuale di oggi, nessun legame con gli ordini aperti.")
        return None
    if req.ordini:
        for o in req.ordini:
            if o not in per_ordine:
                raise b.Stop(f"{o} non e' un ordine aperto del cliente con righe che coprono queste voci.")
        gruppi, assegnate = [], set()
        for o in req.ordini:                       # ogni voce va sul primo ordine elencato che la copre
            e = per_ordine[o]
            voci = [v for v in e["voci"] if v not in assegnate]
            if not voci:
                print(f"  --ordine {o}: tutte le sue voci sono gia' assegnate a un ordine precedente: ignorato.")
                continue
            assegnate.update(voci)
            print(f"  --ordine: la consegna si lega a {o} per {', '.join(voci)}")
            gruppi.append((o, e["righe"], e["data"], voci))
        if len(assegnate) < len(req.voci):
            resto = [v for v, _, _ in req.voci if v not in assegnate]
            print(f"  le altre voci ({', '.join(resto)}) vanno su un ordine manuale.")
        return gruppi
    complete = {o: e for o, e in per_ordine.items()
                if len(e["righe"]) == len(req.voci) and e["data"] is not None
                and abs((e["data"] - req.giorno).days) <= req.finestra_giorni}
    if len(complete) > 1:
        raise b.Stop("piu' ordini aperti del cliente coprono tutte le voci entro "
                     f"{req.finestra_giorni} giorni: {', '.join(sorted(complete))}. Rilancia con --ordine ORD-... "
                     "(quello da evadere) oppure --manuale.")
    if not complete:
        print("  nessun ordine aperto copre tutte le voci in data vicina: creo un ordine manuale.")
        return None
    ordine, e = next(iter(complete.items()))
    print(f"  -> la consegna si lega a {ordine} (prevista {e['data']})")
    return [(ordine, e["righe"], e["data"], e["voci"])]


# --------------------------------------------------------------------------------------------- consegna
def fase_consegna(b, ctx, cid, req: Richiesta, orari: Orari, scelte):
    print(f"\n== CONSEGNA a {req.cliente}")
    fatta = b.audit_fatto(ctx, "CONSEGNA", f"{b.TAG}-consegna-cliente")
    if fatta:
        print(f"  consegna gia' registrata ({fatta}): salto.")
        return fatta
    testo = " + ".join(f"{v} {_n(q)} SET" + (f" ({scelte[v]})" if scelte.get(v) else " (giacenza)")
                       for v, q, _ in req.voci)
    giorno = req.giorno.strftime("%d/%m/%Y")
    reason = f"Consegna a {req.cliente} del {giorno}: " + ", ".join(f"{v} {_n(q)}" for v, q, _ in req.voci) + " SET"
    trovato = trova_ordine(b, ctx, cid, req) if cid else None
    if cid is None:
        print(f"  (anteprima) consegna: {testo} su nuovo ordine manuale (cliente nuovo)")
        return None
    voci_sem = [(v, _n(q), scelte.get(v)) for v, q, _ in req.voci]
    coperte = {v for g in trovato for v in g[3]} if trovato else set()
    manuali = [x for x in voci_sem if x[0] not in coperte]
    legate = [x for x in voci_sem if x[0] in coperte]
    if not ctx.execute:
        if trovato:
            print(f"  (anteprima) consegna: {testo}; legate a {', '.join(g[0] for g in trovato)}: "
                  f"{', '.join(x[0] for x in legate)}"
                  + (f"; su ordine manuale: {', '.join(x[0] for x in manuali)}" if manuali else ""))
        else:
            print(f"  (anteprima) consegna: {testo} su nuovo ordine manuale")
        return None
    righe, planned = [], req.giorno.isoformat()
    if manuali:
        ord_man, righe_man = b.ordine_manuale(
            ctx, cid, manuali, "cliente",
            f"Vendita a {req.cliente} del {giorno}: " + ", ".join(f"{v} {q} SET" for v, q, _ in manuali)
            + (" (fuori dagli ordini aperti)" if trovato else ""))
        righe += b.righe_consegna(ctx, ord_man, righe_man, manuali)
    righe_legate, ordine_voci = [], []
    for ordine, righe_o, data, voci_g in (trovato or []):
        planned = min(planned, str(data))
        voci_sel = [x for x in voci_sem if x[0] in voci_g]
        righe_legate += b.righe_consegna(ctx, ordine, righe_o, voci_sel)
        ordine_voci += voci_sel
    righe = righe_legate + righe
    # la provenienza e' dichiarata solo se nota (da giacenza senza semina: consumo FIFO)
    for r, (_, _, sem) in zip(righe, [*ordine_voci, *manuali]):
        if not sem:
            r.pop("semina", None)
    con = b.consegna(ctx, cid, planned, orari.consegna.isoformat(), righe, "cliente", reason)
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


def fase_pagamento(b, ctx, req: Richiesta, con):
    print("\n== PAGAMENTO ALLA CONSEGNA")
    attivo = pagamento_attivo(ctx, con)
    if attivo:
        print(f"  consegna gia' pagata ({attivo}): salto.")
        return attivo
    if req.metodo is None:
        print("  metodo NON indicato: la consegna resta 'da pagare' (non invento nulla). Quando il cliente paga:")
        print(f"    .venv/bin/python {PAGAMENTI} --pagata {con or 'CON-xxxxxx'} --metodo CONTANTI "
              f"--data {req.giorno.isoformat()} --esegui")
        print("  oppure rilancia questo comando con --metodo BONIFICO|CONTANTI|CARTA|BIZUM|ALTRO --esegui.")
        return None
    key = f"{b.TAG}-pagamento"
    ctx.tpo(["pagamento-consegna", "registra", "--consegna", con or "CON-??????", "--data", req.giorno.isoformat(),
             "--metodo", req.metodo, "--note", f"Pagata alla consegna del {req.giorno.strftime('%d/%m/%Y')} "
             "(dichiarato da Matteo)", "--actor", b.ACTOR, "--reason",
             f"Pagamento alla consegna a {req.cliente} dichiarato da Matteo", "--correlation-id", key,
             "--idempotency-key", key], f"pagamento consegna {con or '(anteprima)'} ({req.metodo})")
    if con and ctx.execute:
        req.pdf_dir.mkdir(parents=True, exist_ok=True)
        ctx.tpo(["bolla", "genera", "--consegna", con, "--output-dir", str(req.pdf_dir), "--per-cliente",
                 "--sovrascrivi"], f"bolla PDF {con} (rigenerata con 'pagado')")
    return pagamento_attivo(ctx, con) if ctx.execute else None


# --------------------------------------------------------------------------------------------- programma
def fase_programma(b, ctx, req: Richiesta, esiste: bool, nome_sistema: str):
    b = carica_base()
    if not req.programma_righe:
        return
    print(f"\n== PROGRAMMA RICORRENTE: ogni {req.programma_ogni} giorni dal {req.programma_prima} "
          f"({', '.join(req.programma_righe)} SET)")
    if not esiste and not ctx.execute:
        print(f"  (anteprima) il cliente non esiste ancora: verra' creato un programma OGNI_X_GIORNI "
              f"{req.programma_ogni} giorni, prima consegna {req.programma_prima}.")
        return
    attivo = ctx.one("""SELECT pf.public_id FROM tpo.programmi_fornitura pf
                        JOIN tpo.programmi_fornitura_versioni v ON v.programma_fornitura_id=pf.id
                        JOIN tpo.clienti c ON c.id=pf.cliente_id
                        WHERE c.denominazione=%s AND v.valida_al IS NULL AND v.stato='ATTIVO'""", (nome_sistema,))
    if attivo:
        print(f"  {nome_sistema} ha gia' il programma ATTIVO {attivo[0]}: salto (per cambiarlo serve una nuova versione).")
        return
    p = carica_programma()
    rc = p.run(ctx.conn, nome_sistema, req.programma_righe, req.programma_prima, req.programma_ogni,
               f"Programma ricorrente di {nome_sistema}: {', '.join(req.programma_righe)} ogni {req.programma_ogni} "
               "giorni (dichiarato da Matteo)", ctx.execute)
    if rc != 0:
        raise b.Stop("il programma non e' stato creato (vedi sopra).")


# --------------------------------------------------------------------------------------------- correttivi
def correttivi(ctx, con):
    print("\n== COMANDI CORRETTIVI (copia solo se serve cambiare qualcosa)")
    pag = pagamento_attivo(ctx, con) if con else None
    if pag:
        print(f"  Pagamento {pag} registrato per errore (metodo/data sbagliati):")
        print(f"    .venv/bin/python {PAGAMENTI} --annulla {pag} --esegui")
        print(f"    poi: ... {PAGAMENTI.split('/')[-1]} --pagata {con} --metodo <METODO> --data AAAA-MM-GG --esegui")
    else:
        print("  Pagamento: nessuno registrato (annullabile con --annulla PGC-... dopo averlo registrato).")
    print("  Consegna, raccolte, transizioni, cliente, programma: registrazioni di autorita' (consegna CONSEGNATA "
          "immutabile).")
    print("  Se qualcosa non torna (quantita', semina, orario) dimmelo e preparo la correzione governata.")


# --------------------------------------------------------------------------------------------- run
def run(ctx, req: Richiesta) -> int:
    b = carica_base()
    b.TAG, b.OGGI, b.WORK = req.tag, req.giorno.isoformat(), WORK / req.tag
    ctx.pdf_dir = req.pdf_dir
    ctx.check_head()
    _STIMATO["v"] = req.giorno != req.oggi or bool(req.ora)
    cid, nome_sistema, da_creare = risolvi_cliente(b, ctx, req)
    base = calcola_base(req, ctx.execute)
    orari = Orari(base)
    salvate = piano_salvato(req).get("semine", {})
    scelte = scegli_semine(b, ctx, req, salvate)
    dichiarate = {s for s, _ in req.pronte}

    # tutti i controlli PRIMA di scrivere qualsiasi cosa
    controlla_giacenze(b, ctx, req)
    piani = {}
    for semina, dich in req.pronte:
        piani[semina] = piano_pronta(b, ctx, orari, semina, dich)
    for varieta, qty, _ in req.voci:
        if _fold(varieta) not in req.da_giacenza:
            verifica_raccolta(b, ctx, req, orari, varieta, qty, scelte[varieta], dichiarate)
    if cid and not b.audit_fatto(ctx, "CONSEGNA", f"{b.TAG}-consegna-cliente"):
        trova_ordine(b, ctx, cid, req)                 # ambiguita' = stop prima di scrivere
    if ctx.execute:
        salva_piano(req, base, scelte)

    if da_creare:
        if ctx.execute:
            cid = crea_cliente(b, ctx, req)
        else:
            print("\n== CLIENTE NUOVO: (anteprima) verra' creato senza dati fiscali.")
    for semina, piano in piani.items():
        if piano is not None:
            applica_pronta(b, ctx, semina, *piano)
    fase_raccolte(b, ctx, req, orari, scelte, dichiarate)
    con = fase_consegna(b, ctx, cid, req, orari, scelte)
    if con is None and ctx.execute:
        raise b.Stop("consegna non registrata")
    fase_pagamento(b, ctx, req, con)
    fase_programma(b, ctx, req, not da_creare or ctx.execute, nome_sistema)
    correttivi(ctx, con)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cliente", help='nome (es. "La Jaira") o id CLI-000000')
    ap.add_argument("voci", nargs="+", metavar="Varieta:SET[:SEM-000000]")
    ap.add_argument("--giorno", help="AAAA-MM-GG (default oggi); per un giorno passato serve --ora")
    ap.add_argument("--ora", help="HH:MM della prima operazione (pronta o raccolte)")
    ap.add_argument("--metodo", choices=METODI)
    ap.add_argument("--pronta", action="append", default=[], metavar="SEM-000000:SET")
    ap.add_argument("--da-giacenza", action="append", default=[], metavar="VARIETA")
    ap.add_argument("--oltre-attesi", action="store_true")
    ap.add_argument("--nuovo-cliente", action="store_true")
    ap.add_argument("--anche-se-simile", action="store_true")
    ap.add_argument("--ordine", metavar="ORD-000000", action="append",
                    help="ripetibile: ogni voce va sul primo ordine elencato che la copre")
    ap.add_argument("--manuale", action="store_true")
    ap.add_argument("--finestra-giorni", type=int, default=3)
    ap.add_argument("--programma-riga", action="append", default=[], metavar="VARIETA:SET")
    ap.add_argument("--programma-prima", metavar="AAAA-MM-GG")
    ap.add_argument("--programma-ogni", type=int, default=14)
    ap.add_argument("--replica", type=int, default=1)
    ap.add_argument("--pdf-dir", default=str(Path.home() / "Desktop" / "bolle"))
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    b = carica_base()
    try:
        req = Richiesta(
            a.cliente, a.voci, giorno=date.fromisoformat(a.giorno) if a.giorno else None, ora=a.ora,
            metodo=a.metodo, pronte=a.pronta, da_giacenza=a.da_giacenza, oltre_attesi=a.oltre_attesi,
            nuovo_cliente=a.nuovo_cliente, anche_se_simile=a.anche_se_simile, ordine=a.ordine, manuale=a.manuale,
            finestra_giorni=a.finestra_giorni, programma_righe=a.programma_riga,
            programma_prima=date.fromisoformat(a.programma_prima) if a.programma_prima else None,
            programma_ogni=a.programma_ogni, replica=a.replica, pdf_dir=a.pdf_dir)
    except b.Stop as exc:
        print(f"\nSTOP: {exc}", file=sys.stderr)
        return 1
    ctx = b.Ctx(a.esegui, req.pdf_dir)
    try:
        print(f"== CONSEGNA {req.cliente} {req.giorno:%d/%m/%Y} -- "
              f"{'ESECUZIONE' if a.esegui else 'ANTEPRIMA (nulla viene scritto)'}")
        run(ctx, req)
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
