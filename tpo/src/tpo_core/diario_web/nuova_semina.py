"""Schermata NUOVA SEMINA del diario (21/10/2026): registrare una semina di microgreens scegliendo la varieta' da una
lista, i SET, il giorno e l'ora, senza passare dal terminale (richiesta di Matteo, 21/10/2026).

E' la stessa procedura governata che finora si faceva con `scripts/commissioning/2026-10-12_semine.py`:
  1. `tpo semina commission` (stato AVVIATA, origine RIPRISTINO_STOCK, nessun cliente/ordine: si collega dopo);
     grammi = g/SET del protocollo APPROVATO corrente x SET, presi dal lotto di seme scelto;
  2. consumo materiali (`tpo materiali consumo-semina`): 4 vaschette + 4 substrati per SET.
Nessuna regola di dominio nuova qui: le regole le applicano i comandi governati. Qui si leggono i dati, si mostra
l'anteprima ESATTA e, dopo la conferma, si rileggono i dati un istante prima di scrivere (mai fidarsi della proposta).

Differenze volute rispetto alla semina "a parole" (actions.prepara_commission):
- e' una scelta da lista, quindi anche chi non ha un protocollo o un lotto utilizzabile compare, con il MOTIVO per cui
  non si puo' ancora seminare (invece di sparire);
- se i lotti utilizzabili sono piu' di uno si puo' scegliere (di default quello che sceglievano gli script);
- il consumo dei materiali e' compreso. Idempotente: se la conferma viene ripetuta (doppio tocco, rete lenta) la semina
  gia' registrata allo stesso istante NON viene duplicata e i materiali, se mancavano, si completano.
Solo microgreens (unita' SET, interi). La Towerfarm (grammi/unita') non c'e' ancora: va prima concordata.
"""
from __future__ import annotations

import re
from argparse import Namespace
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Sequence

from ..cli.consumo_materiali import run_consumo_materiali_command
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from . import db_context, magazzino
from .actions import PropostaAmbigua, SeminaOperazioneFallita, TZ_LOCALE, _esegui, _n

ORIGINE = "RIPRISTINO_STOCK"
PEZZI_PER_SET = 4
SET_MAX = 50                       # tetto di buon senso contro un refuso (es. 20 invece di 2)
ORA_GIORNO_PASSATO = time(12, 0)   # stessa regola dei cambi di stadio: orario non osservato
GIORNI_INDIETRO_MAX = 31

SQL_VARIETA = ("SELECT public_id, denominazione, codice_tracciabilita FROM tpo.varieta "
               "WHERE stato = 'ATTIVA' ORDER BY lower(denominazione)")

SQL_PROTOCOLLI = """SELECT v.public_id, pv.public_id, pv.grammi_seme_per_set
FROM tpo.varieta v
JOIN tpo.cultivar c ON c.varieta_id = v.id
JOIN tpo.cultivar_usi cu ON cu.cultivar_id = c.id
JOIN tpo.usi_produttivi up ON up.id = cu.uso_produttivo_id AND up.codice = 'MICROGREEN'
JOIN tpo.protocolli p ON p.cultivar_uso_id = cu.id
JOIN tpo.protocollo_versioni pv ON pv.protocollo_id = p.id
WHERE v.stato = 'ATTIVA' AND pv.stato_approvazione = 'APPROVATA' AND pv.valida_al IS NULL
ORDER BY v.public_id, pv.public_id"""

# Come gli script di semina: impieghi RACCOMANDATA/UTILIZZABILE, prima i raccomandati e meglio valutati, poi il lotto
# ricevuto per ultimo. DISTINCT ON: un lotto compare una volta sola anche con piu' impieghi.
SQL_LOTTI = """SELECT DISTINCT ON (v.public_id, ls.public_id)
       v.public_id, ls.public_id, ls.version, s.fornitore, s.referenza_commerciale, ls.quantita_residua,
       ls.data_scadenza, ls.anomalia, si.raccomandazione::text, si.rating, ls.data_ricezione
FROM tpo.semente_impieghi si
JOIN tpo.sementi s ON s.id = si.semente_id
JOIN tpo.lotti_seme ls ON ls.semente_id = s.id
JOIN tpo.cultivar_usi cu ON cu.id = si.cultivar_uso_id
JOIN tpo.cultivar c ON c.id = cu.cultivar_id
JOIN tpo.varieta v ON v.id = c.varieta_id
WHERE si.raccomandazione IN ('RACCOMANDATA', 'UTILIZZABILE') AND ls.quantita_residua > 0
ORDER BY v.public_id, ls.public_id, si.raccomandazione, si.rating DESC NULLS LAST"""

SQL_SEMINE_DEL_GIORNO = """SELECT s.public_id, s.codice_tracciabilita, s.data_avvio, s.expected_useful_quantity,
       s.expected_useful_uom::text
FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id
WHERE v.public_id = %s AND s.data_avvio >= %s AND s.data_avvio < %s
ORDER BY s.data_avvio"""


@dataclass(frozen=True)
class Lotto:
    public_id: str
    version: int
    fornitore: str
    referenza: str
    residuo: Decimal
    scadenza: date | None
    anomalia: str | None
    raccomandazione: str
    rating: Decimal | None = None
    ricevuto: date | None = None


@dataclass(frozen=True)
class VarietaOpzione:
    public_id: str
    nome: str
    codice: str
    protocolli: tuple[tuple[str, Decimal], ...] = ()      # (versione protocollo, g/SET) APPROVATI correnti
    lotti: tuple[Lotto, ...] = ()


@dataclass(frozen=True)
class SeminaEsistente:
    public_id: str
    codice: str | None
    data_avvio: datetime
    set_attesi: Decimal | None
    unita: str | None


@dataclass(frozen=True)
class PropostaNuovaSemina:
    varieta_public_id: str
    varieta_nome: str
    num_set: str
    grammi: str
    g_per_set: str
    lotto_seme_public_id: str
    lotto_fornitore: str
    protocollo_versione_public_id: str
    physical_started_at: str
    residuo_dopo: str
    vaschette: str
    substrati: str
    note: list[str] = field(default_factory=list)
    tipo: str = field(default="nuova_semina", init=False)


# ---------------------------------------------------------------- lettura

def componi_opzioni(varieta: Sequence[Sequence[Any]], protocolli: Sequence[Sequence[Any]],
                    lotti: Sequence[Sequence[Any]]) -> list[VarietaOpzione]:
    """Funzione pura: unisce le tre letture. Una varieta' senza protocollo o senza lotto compare lo stesso."""
    prot: dict[str, list[tuple[str, Decimal]]] = {}
    for vid, pv, g in protocolli:
        prot.setdefault(vid, []).append((pv, Decimal(g)))
    per_var: dict[str, list[Lotto]] = {}
    for vid, lse, version, forn, ref, residuo, scad, anom, racc, rating, ricevuto in lotti:
        per_var.setdefault(vid, []).append(Lotto(
            lse, int(version), forn, ref, Decimal(residuo), scad, anom or None, racc,
            Decimal(rating) if rating is not None else None, ricevuto))
    risultato = []
    for vid, nome, codice in varieta:
        ordinati = sorted(per_var.get(vid, []), key=_chiave_lotto)
        risultato.append(VarietaOpzione(vid, nome, codice, tuple(prot.get(vid, ())), tuple(ordinati)))
    return risultato


def _chiave_lotto(l: Lotto):
    """Stesso ordine degli script: RACCOMANDATA prima di UTILIZZABILE, rating alto, ricevuto per ultimo."""
    ricevuto = l.ricevuto.toordinal() if l.ricevuto else 0
    return (l.raccomandazione, -(l.rating if l.rating is not None else Decimal(-1)), -ricevuto, l.public_id)


def leggi_opzioni(settings: PostgreSQLSettings) -> list[VarietaOpzione]:
    with db_context._connect(settings) as conn, conn.cursor() as cur:
        conn.read_only = True
        cur.execute(SQL_VARIETA)
        varieta = cur.fetchall()
        cur.execute(SQL_PROTOCOLLI)
        protocolli = cur.fetchall()
        cur.execute(SQL_LOTTI)
        lotti = cur.fetchall()
    return componi_opzioni(varieta, protocolli, lotti)


def leggi_stock(settings: PostgreSQLSettings) -> dict[str, Decimal | None]:
    """Giacenza di vaschette e substrato a sistema (stessi nomi riconosciuti dalla schermata Magazzino)."""
    with db_context._connect(settings) as conn, conn.cursor() as cur:
        conn.read_only = True
        cur.execute(magazzino.SQL_ARTICOLI)
        righe = cur.fetchall()
    stock: dict[str, Decimal | None] = {"vaschette": None, "substrato": None}
    for _codice, nome, uom, disponibile, _ultimo in righe:
        f = magazzino._fold(nome)
        if uom != "UNIT":
            continue
        if "vaschett" in f:
            stock["vaschette"] = Decimal(disponibile)
        elif "substrat" in f:
            stock["substrato"] = Decimal(disponibile)
    return stock


def semine_del_giorno(settings: PostgreSQLSettings, varieta_public_id: str, giorno: date) -> list[SeminaEsistente]:
    inizio = datetime.combine(giorno, time(0, 0), TZ_LOCALE)
    fine = datetime.combine(giorno + timedelta(days=1), time(0, 0), TZ_LOCALE)
    with db_context._connect(settings) as conn, conn.cursor() as cur:
        conn.read_only = True
        cur.execute(SQL_SEMINE_DEL_GIORNO, (varieta_public_id, inizio, fine))
        return [SeminaEsistente(pid, codice, avvio, Decimal(q) if q is not None else None, uom)
                for pid, codice, avvio, q, uom in cur.fetchall()]


# ---------------------------------------------------------------- regole (pure)

def motivo_lotto(l: Lotto, g_per_set: Decimal, giorno: date, num_set: int = 1) -> str | None:
    """Perche' questo lotto NON si puo' usare (None = utilizzabile)."""
    if l.anomalia:
        return "ha una nota di anomalia: va corretta prima di poterlo usare"
    if l.scadenza is not None and l.scadenza < giorno:
        return f"scaduto il {l.scadenza:%d/%m/%Y}"
    serve = g_per_set * num_set
    if l.residuo < serve:
        return f"residuo {_n(l.residuo)} g, ne servono {_n(serve)} g"
    return None


def motivo_varieta(v: VarietaOpzione, giorno: date, num_set: int = 1) -> str | None:
    """Perche' la varieta' non si puo' seminare (None = si puo')."""
    if not v.protocolli:
        return "manca un protocollo approvato corrente (va creato prima)"
    if len(v.protocolli) > 1:
        return f"ha {len(v.protocolli)} protocolli correnti: ne serve uno solo (da sistemare)"
    if not v.lotti:
        return "nessun lotto di seme collegato con seme disponibile"
    g_per_set = v.protocolli[0][1]
    motivi = [motivo_lotto(l, g_per_set, giorno, num_set) for l in v.lotti]
    if all(motivi):
        return "nessun lotto utilizzabile: " + "; ".join(
            f"{l.public_id} {m}" for l, m in zip(v.lotti, motivi))
    return None


def lotto_predefinito(v: VarietaOpzione, giorno: date, num_set: int) -> Lotto | None:
    g_per_set = v.protocolli[0][1]
    return next((l for l in v.lotti if motivo_lotto(l, g_per_set, giorno, num_set) is None), None)


def a_dizionario(opzioni: Sequence[VarietaOpzione], oggi: date) -> dict:
    out = []
    for v in opzioni:
        motivo = motivo_varieta(v, oggi)
        g = v.protocolli[0][1] if len(v.protocolli) == 1 else None
        lotti = []
        for l in v.lotti:
            m = motivo_lotto(l, g, oggi) if g is not None else "senza protocollo"
            lotti.append({
                "lotto": l.public_id, "fornitore": l.fornitore, "referenza": l.referenza, "residuo": _n(l.residuo),
                "scadenza": l.scadenza.isoformat() if l.scadenza else None, "utilizzabile": m is None,
                "motivo": m, "max_set": int(l.residuo // g) if g else 0,
            })
        out.append({"varieta": v.public_id, "nome": v.nome, "codice": v.codice, "pronta": motivo is None,
                    "motivo": motivo, "g_per_set": _n(g) if g is not None else None,
                    "protocollo": v.protocolli[0][0] if len(v.protocolli) == 1 else None, "lotti": lotti})
    pronte = [x for x in out if x["pronta"]]
    return {"oggi": oggi.isoformat(), "set_max": SET_MAX, "pezzi_per_set": PEZZI_PER_SET,
            "varieta": pronte + [x for x in out if not x["pronta"]]}


def _intero(nome: str, testo: Any, minimo: int, massimo: int) -> int:
    try:
        d = Decimal(str(testo).replace(",", ".").strip())
    except Exception:  # noqa: BLE001 -- Decimal solleva eccezioni diverse sul testo non numerico
        raise PropostaAmbigua(f"{nome}: '{testo}' non e' un numero.") from None
    if not d.is_finite() or d != d.to_integral_value():
        raise PropostaAmbigua(f"{nome}: servono SET interi (hai scritto '{testo}').")
    n = int(d)
    if n < minimo:
        raise PropostaAmbigua(f"{nome}: almeno {minimo}.")
    if n > massimo:
        raise PropostaAmbigua(f"{nome}: {n} sembra troppo (massimo {massimo}): controlla di non aver sbagliato.")
    return n


def istante_avvio(giorno: date, ora: time | None, adesso: datetime) -> tuple[datetime, list[str]]:
    """Istante fisico di semina, in ora delle Canarie (ora legale compresa). Oggi senza ora = adesso; un giorno passato
    senza ora = 12:00 (orario non osservato, come nei cambi di stadio). Mai nel futuro."""
    adesso = adesso.astimezone(TZ_LOCALE)
    oggi = adesso.date()
    if giorno > oggi:
        raise PropostaAmbigua(f"{giorno:%d/%m/%Y} e' nel futuro: la semina si registra dopo averla fatta.")
    if (oggi - giorno).days > GIORNI_INDIETRO_MAX:
        raise PropostaAmbigua(f"{giorno:%d/%m/%Y} e' troppo indietro (oltre {GIORNI_INDIETRO_MAX} giorni): controlla la data.")
    note = []
    if ora is None:
        if giorno == oggi:
            quando = adesso.replace(second=0, microsecond=0)
            note.append(f"Ora non indicata: vale adesso ({quando:%H:%M}).")
        else:
            quando = datetime.combine(giorno, ORA_GIORNO_PASSATO, TZ_LOCALE)
            note.append("Ora non indicata: vale 12:00 (orario non osservato).")
    else:
        quando = datetime.combine(giorno, ora.replace(second=0, microsecond=0), TZ_LOCALE)
    if quando > adesso + timedelta(minutes=1):
        raise PropostaAmbigua(f"Le {quando:%H:%M} di oggi non sono ancora arrivate: la semina si registra dopo averla fatta.")
    return quando, note


# ---------------------------------------------------------------- anteprima

def prepara(settings: PostgreSQLSettings, varieta_public_id: str, num_set: Any, giorno: date, ora: time | None,
            lotto: str | None = None, adesso: datetime | None = None) -> PropostaNuovaSemina:
    adesso = adesso or datetime.now(TZ_LOCALE)
    n = _intero("SET", num_set, 1, SET_MAX)
    quando, note = istante_avvio(giorno, ora, adesso)
    v = _varieta(leggi_opzioni(settings), varieta_public_id)
    motivo = motivo_varieta(v, giorno, n)
    if motivo and (not v.protocolli or len(v.protocolli) > 1 or not v.lotti):
        raise PropostaAmbigua(f"{v.nome}: {motivo}.")
    pv, g_per_set = v.protocolli[0]
    scelto = _lotto(v, lotto, g_per_set, giorno, n)
    grammi = g_per_set * n
    note += _note_confronto(settings, v, giorno, quando)
    stock = leggi_stock(settings)
    for chiave, nome in (("vaschette", "vaschette"), ("substrato", "substrati")):
        disponibile, serve = stock.get(chiave), Decimal(PEZZI_PER_SET * n)
        if disponibile is not None and disponibile < serve:
            note.append(f"Attenzione: a sistema ci sono solo {_n(disponibile)} {nome}, ne servono {_n(serve)}: "
                        "lo scarico dei materiali potrebbe essere rifiutato.")
    return PropostaNuovaSemina(
        varieta_public_id=v.public_id, varieta_nome=v.nome, num_set=str(n), grammi=_n(grammi), g_per_set=_n(g_per_set),
        lotto_seme_public_id=scelto.public_id, lotto_fornitore=scelto.fornitore, protocollo_versione_public_id=pv,
        physical_started_at=quando.isoformat(), residuo_dopo=_n(scelto.residuo - grammi),
        vaschette=str(PEZZI_PER_SET * n), substrati=str(PEZZI_PER_SET * n), note=note)


def _varieta(opzioni: Sequence[VarietaOpzione], public_id: str) -> VarietaOpzione:
    v = next((x for x in opzioni if x.public_id == public_id), None)
    if v is None:
        raise PropostaAmbigua(f"Varieta' {public_id} non trovata o non attiva.")
    return v


def _lotto(v: VarietaOpzione, richiesto: str | None, g_per_set: Decimal, giorno: date, n: int) -> Lotto:
    if richiesto:
        l = next((x for x in v.lotti if x.public_id == richiesto), None)
        if l is None:
            raise PropostaAmbigua(f"{richiesto} non e' un lotto collegato a {v.nome}.")
        m = motivo_lotto(l, g_per_set, giorno, n)
        if m:
            raise PropostaAmbigua(f"{v.nome}: il lotto {l.public_id} non si puo' usare: {m}.")
        return l
    l = lotto_predefinito(v, giorno, n)
    if l is None:
        elenco = "; ".join(f"{x.public_id} {motivo_lotto(x, g_per_set, giorno, n)}" for x in v.lotti)
        raise PropostaAmbigua(f"{v.nome}: nessun lotto utilizzabile per {n} SET ({elenco}).")
    return l


def _note_confronto(settings: PostgreSQLSettings, v: VarietaOpzione, giorno: date, quando: datetime) -> list[str]:
    note = []
    for s in semine_del_giorno(settings, v.public_id, giorno):
        stesso = abs((s.data_avvio - quando).total_seconds()) < 1
        cosa = f"{s.codice or s.public_id}" + (f", {_n(s.set_attesi)} {s.unita}" if s.set_attesi is not None else "")
        if stesso:
            note.append(f"Esiste gia' una semina di {v.nome} esattamente a quest'ora ({cosa}): se confermi NON si "
                        "duplica, si completano solo gli eventuali materiali mancanti.")
        else:
            note.append(f"Lo stesso giorno risulta gia' una semina di {v.nome} ({cosa}, "
                        f"{s.data_avvio.astimezone(TZ_LOCALE):%H:%M}): se e' una seconda semina va bene, altrimenti annulla.")
    return note


# ---------------------------------------------------------------- esecuzione

def esegui(settings: PostgreSQLSettings, p: PropostaNuovaSemina, actor: str, adesso: datetime | None = None) -> str:
    """Rilegge tutto dal database e scrive. La proposta arrivata dalla pagina serve solo a sapere COSA si e' confermato:
    protocollo, lotto, grammi e istante vengono ricontrollati e, se qualcosa e' cambiato, non si scrive nulla."""
    adesso = adesso or datetime.now(TZ_LOCALE)
    try:
        n = _intero("SET", p.num_set, 1, SET_MAX)
        quando = datetime.fromisoformat(p.physical_started_at)
    except (PropostaAmbigua, ValueError) as exc:
        raise SeminaOperazioneFallita(f"Proposta non valida ({exc}). Nulla registrato.") from None
    if quando.tzinfo is None or quando > adesso + timedelta(minutes=1):
        raise SeminaOperazioneFallita("Istante non valido o nel futuro: nulla registrato.")
    giorno = quando.astimezone(TZ_LOCALE).date()
    try:
        v = _varieta(leggi_opzioni(settings), p.varieta_public_id)
        if len(v.protocolli) != 1:
            raise PropostaAmbigua(f"{v.nome}: {motivo_varieta(v, giorno, n)}.")
        pv, g_per_set = v.protocolli[0]
        if pv != p.protocollo_versione_public_id or _n(g_per_set * n) != p.grammi:
            raise PropostaAmbigua(f"{v.nome}: il protocollo e' cambiato dopo l'anteprima ({pv}, {_n(g_per_set)} g/SET). "
                                  "Prepara di nuovo la semina.")
        lotto = _lotto(v, p.lotto_seme_public_id, g_per_set, giorno, n)
    except PropostaAmbigua as exc:
        raise SeminaOperazioneFallita(f"{exc} Nulla registrato.") from None

    esistente = next((s for s in semine_del_giorno(settings, v.public_id, giorno)
                      if abs((s.data_avvio - quando).total_seconds()) < 1), None)
    marca = quando.astimezone(timezone.utc).strftime("%Y%m%dT%H%M")
    if esistente is not None:
        semina, codice, prefisso = esistente.public_id, esistente.codice or "", "Semina gia' registrata"
    else:
        quando_txt = quando.astimezone(TZ_LOCALE)
        args = Namespace(
            semina_command="commission", seed_lot=lotto.public_id, expected_seed_lot_version=lotto.version,
            protocol_version=pv, actual_seed_grams=p.grammi, physical_started_at=quando.isoformat(), origin=ORIGINE,
            planning_line=None, expected_planning_line_version=None, started_quantity_set=None,
            provenance='{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED",'
                       '"selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}',
            actor=actor,
            reason=(f"Semina reale {v.nome} del {quando_txt:%d/%m/%Y} ore {quando_txt:%H:%M} ({n} SET, {p.grammi} g), "
                    f"registrata dal diario da {actor}; cliente/ordine da assegnare in seguito."),
            correlation_id=f"DIARIO-NUOVA-SEMINA-{v.public_id}-{marca}",
            idempotency_key=f"diario-nuova-semina-{v.public_id.lower()}-{marca}-{n}-{lotto.public_id.lower()}",
            confirm=True)
        testo = _esegui(args)
        m_id, m_cod = re.search(r"PUBLIC_ID:\s*(SEM-\d+)", testo), re.search(r"TRACEABILITY_CODE:\s*(\S+)", testo)
        if not m_id:
            raise SeminaOperazioneFallita(f"Semina scritta ma risposta non riconosciuta: controlla il Magazzino.\n{testo}")
        semina, codice, prefisso = m_id.group(1), (m_cod.group(1) if m_cod else ""), "Semina registrata"
    etichetta = f"{codice} ({semina})" if codice else semina
    try:
        _consuma_materiali(semina, n, actor, marca)
    except SeminaOperazioneFallita as exc:
        raise SeminaOperazioneFallita(
            f"{prefisso}: {etichetta}, {n} SET {v.nome}. MA i materiali NON sono stati scalati: {exc}\n"
            "La semina e' al sicuro. Per completare i materiali basta confermare di nuovo la stessa semina "
            "(non si duplica nulla).") from None
    return (f"{prefisso}: {etichetta} — {n} SET {v.nome}, {p.grammi} g dal lotto {lotto.public_id} "
            f"(residuo {_n(lotto.residuo - Decimal(p.grammi)) if esistente is None else _n(lotto.residuo)} g).\n"
            f"Materiali scalati: {PEZZI_PER_SET * n} vaschette + {PEZZI_PER_SET * n} substrati.")


def _consuma_materiali(semina: str, n: int, actor: str, marca: str) -> None:
    import io
    out, err = io.StringIO(), io.StringIO()
    args = Namespace(
        materiali_command="consumo-semina", semina=semina, set_seminati=n, pezzi_per_set=PEZZI_PER_SET,
        articolo_vaschette=None, articolo_substrato=None, effective_at=None, actor=actor,
        reason=f"Consumo materiali semina {semina}: {n} SET x {PEZZI_PER_SET} pezzi, registrato dal diario",
        correlation_id=f"DIARIO-CONSUMO-{semina}", confirm=True)
    codice = run_consumo_materiali_command(args, stdout=out, stderr=err)
    if codice != 0:
        raise SeminaOperazioneFallita((err.getvalue() or out.getvalue() or f"codice {codice}").strip())


def a_dizionario_proposta(p: PropostaNuovaSemina) -> dict:
    return asdict(p) | {"tipo": p.tipo}
