"""Piano delle SESSIONI DI SEMINA: le semine da fare raggruppate in due giorni fissi della settimana (default
mercoledi e domenica), per varieta', con il totale da seminare e "per chi" (richiesta di Matteo, 16/10/2026: "non posso
piantare oggi 1 set per un cliente e domani 2 per un altro: semino direttamente la domenica o il mercoledi").

Sola lettura. Non calcola nulla di nuovo sul DOMINIO: la data ideale di semina di ogni riga (`sowing_at`), la quantita'
da avviare (gia' al netto di stock, semine in corso e buffer) e i grammi di seme li ha gia' scritti il motore di
Production Planning; qui si leggono e si raggruppano. Il filtro "cosa e' ancora da seminare" e' lo stesso del reader
"Da seminare" (FROM_WHERE_DA_SEMINARE).

Regola di assegnazione (default prudente, scritta qui perche' e' una scelta di Matteo da rivedere):
- una riga va alla sessione PRECEDENTE (o uguale) alla sua data ideale: si semina in ANTICIPO, mai in ritardo, cosi' il
  prodotto e' pronto per la consegna. L'anticipo massimo con mercoledi+domenica e' di 3 giorni.
- se quella sessione e' gia' passata (o la data ideale e' gia' passata) la riga va alla PROSSIMA sessione utile ed e'
  segnata IN RITARDO di N giorni sul piano: per quel caso puoi decidere di seminare fuori sessione.
- ORDINI SCADUTI (consegna prevista gia' passata, ordine ancora aperto: di solito un residuo da chiudere) e righe il
  cui ritardo supera `ritardo_max` giorni (una semina nuova non puo' piu' rispettare la consegna: serve una decisione,
  es. coperto da giacenza o semine in corso, consegna da spostare) NON entrano nelle sessioni: sono elencati a parte,
  per ordine, cosi' il recap resta leggibile. ANTICIPO oltre `anticipo_max` giorni e ritardi piccoli restano segnalati.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..infrastructure.postgresql.pianificazione_semina_lettura import FROM_WHERE_DA_SEMINARE
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from . import db_context

TZ = ZoneInfo("Atlantic/Canary")
GIORNI_DEFAULT = (3, 7)                    # isoweekday: mercoledi, domenica
NOMI_GIORNO = ("lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica")
ANTICIPO_MAX_DEFAULT = 3
RITARDO_MAX_DEFAULT = 7

_SELECT = (
    "SELECT rps.public_id, v.denominazione, c.denominazione, o.public_id, o.data_consegna_prevista, rps.stato, "
    "rps.quantita_residua_da_avviare, rps.unita_domanda, rps.grammi_seme_richiesti, rps.sowing_at, rps.data_consegna, o.stato "
    + FROM_WHERE_DA_SEMINARE + " ORDER BY rps.sowing_at, v.denominazione, c.denominazione"
)


@dataclass(frozen=True)
class RigaSemina:
    riga: str
    varieta: str
    cliente: str
    ordine: str
    ordine_consegna: date | None
    stato: str
    quantita: Decimal
    unita: str
    grammi: Decimal
    data_ideale: date           # giorno di semina calcolato dal motore (fuso Canarie)
    consegna: date
    ordine_stato: str = ""      # APERTO / PARZIALMENTE_EVASO


@dataclass(frozen=True)
class Destinatario:
    cliente: str
    quantita: Decimal
    consegna: date
    ordine: str
    ritardo_giorni: int = 0
    anticipo_giorni: int = 0
    note: tuple[str, ...] = ()


@dataclass(frozen=True)
class VarietaDaSeminare:
    varieta: str
    unita: str
    quantita: Decimal
    grammi: Decimal
    destinatari: tuple[Destinatario, ...]


@dataclass(frozen=True)
class Sessione:
    data: date
    varieta: tuple[VarietaDaSeminare, ...]

    @property
    def nome_giorno(self) -> str:
        return NOMI_GIORNO[self.data.weekday()]

    @property
    def quantita_per_unita(self) -> dict[str, Decimal]:
        totali: dict[str, Decimal] = defaultdict(Decimal)
        for v in self.varieta:
            totali[v.unita] += v.quantita
        return dict(totali)


@dataclass(frozen=True)
class OrdineDaVerificare:
    ordine: str
    cliente: str
    consegna: date
    ritardo_giorni: int                          # 0 per gli ordini scaduti
    voci: tuple[str, ...]                        # "Afila 1 SET"
    stato: str = ""                              # stato dell'ordine


@dataclass(frozen=True)
class PianoSessioni:
    oggi: date
    giorni: tuple[int, ...]
    sessioni: tuple[Sessione, ...]               # le prime `n_sessioni` richieste
    piu_avanti: int                              # righe assegnate a sessioni successive
    ultima_data_piu_avanti: date | None
    scaduti: tuple[OrdineDaVerificare, ...] = field(default=())          # consegna passata, ordine ancora aperto
    da_verificare: tuple[OrdineDaVerificare, ...] = field(default=())    # ritardo > ritardo_max


def leggi_righe(cur) -> list[RigaSemina]:
    cur.execute(_SELECT)
    righe = []
    for riga, varieta, cliente, ordine, ord_cons, stato, qty, unita, grammi, sowing_at, consegna, ord_stato in cur.fetchall():
        righe.append(RigaSemina(
            riga=riga, varieta=varieta, cliente=cliente, ordine=ordine, ordine_consegna=ord_cons, stato=stato,
            quantita=Decimal(qty), unita=unita, grammi=Decimal(grammi),
            data_ideale=sowing_at.astimezone(TZ).date(), consegna=consegna, ordine_stato=ord_stato))
    return righe


def _sessione_dal(giorno: date, giorni: tuple[int, ...]) -> date:
    """Primo giorno >= `giorno` che e' una sessione."""
    for i in range(8):
        d = giorno + timedelta(days=i)
        if d.isoweekday() in giorni:
            return d
    raise ValueError("nessun giorno di sessione")


def _sessione_fino_a(giorno: date, giorni: tuple[int, ...]) -> date:
    """Ultimo giorno <= `giorno` che e' una sessione."""
    for i in range(8):
        d = giorno - timedelta(days=i)
        if d.isoweekday() in giorni:
            return d
    raise ValueError("nessun giorno di sessione")


def _per_ordine(items: list[tuple[RigaSemina, int]]) -> tuple[OrdineDaVerificare, ...]:
    gruppi: dict[str, list[tuple[RigaSemina, int]]] = defaultdict(list)
    for item in items:
        gruppi[item[0].ordine].append(item)
    out = []
    for ordine, righe in gruppi.items():
        prima = righe[0][0]
        voci = [f"{r.varieta} {_n(r.quantita)} {r.unita}" for r, _ in sorted(righe, key=lambda x: x[0].varieta)]
        out.append(OrdineDaVerificare(ordine, prima.cliente, prima.ordine_consegna or prima.consegna,
                                      max(rit for _, rit in righe), tuple(voci), prima.ordine_stato))
    return tuple(sorted(out, key=lambda o: (o.consegna, o.ordine)))


def assegna(righe: list[RigaSemina], oggi: date, giorni: tuple[int, ...] = GIORNI_DEFAULT,
            n_sessioni: int = 2, anticipo_max: int = ANTICIPO_MAX_DEFAULT,
            ritardo_max: int = RITARDO_MAX_DEFAULT) -> PianoSessioni:
    giorni = tuple(sorted(set(giorni)))
    assegnate: dict[date, list[tuple[RigaSemina, int, int]]] = defaultdict(list)     # (riga, ritardo, anticipo)
    scaduti: list[tuple[RigaSemina, int]] = []
    da_verificare: list[tuple[RigaSemina, int]] = []
    for r in righe:
        if r.data_ideale < oggi:
            sess = _sessione_dal(oggi, giorni)
        else:
            prec = _sessione_fino_a(r.data_ideale, giorni)
            sess = prec if prec >= oggi else _sessione_dal(oggi, giorni)
        ritardo = max(0, (sess - r.data_ideale).days)
        anticipo = max(0, (r.data_ideale - sess).days)
        if (r.ordine_consegna is not None and r.ordine_consegna < oggi) or r.consegna < oggi:
            scaduti.append((r, 0))
        elif ritardo > ritardo_max:
            da_verificare.append((r, ritardo))
        else:
            assegnate[sess].append((r, ritardo, anticipo))

    date_ordinate = sorted(assegnate)
    mostrate, successive = date_ordinate[:n_sessioni], date_ordinate[n_sessioni:]
    sessioni = []
    for data in mostrate:
        per_varieta: dict[tuple[str, str], list[tuple[RigaSemina, int, int]]] = defaultdict(list)
        for item in assegnate[data]:
            per_varieta[(item[0].varieta, item[0].unita)].append(item)
        varieta = []
        for (nome, unita), items in sorted(per_varieta.items()):
            dest = []
            for r, ritardo, anticipo in sorted(items, key=lambda x: (x[0].consegna, x[0].cliente)):
                note = []
                if ritardo:
                    note.append(f"in ritardo di {ritardo} gg sul piano")
                if anticipo > anticipo_max:
                    note.append(f"ANTICIPO di {anticipo} gg")
                dest.append(Destinatario(r.cliente, r.quantita, r.consegna, r.ordine, ritardo, anticipo, tuple(note)))
            varieta.append(VarietaDaSeminare(
                nome, unita, sum((i[0].quantita for i in items), Decimal(0)),
                sum((i[0].grammi for i in items), Decimal(0)), tuple(dest)))
        sessioni.append(Sessione(data, tuple(varieta)))
    piu_avanti = sum(len(assegnate[d]) for d in successive)
    return PianoSessioni(oggi, giorni, tuple(sessioni), piu_avanti, successive[-1] if successive else None,
                         _per_ordine(scaduti), _per_ordine(da_verificare))


def piano(settings: PostgreSQLSettings, oggi: date | None = None, giorni: tuple[int, ...] = GIORNI_DEFAULT,
          n_sessioni: int = 2, anticipo_max: int = ANTICIPO_MAX_DEFAULT,
          ritardo_max: int = RITARDO_MAX_DEFAULT) -> PianoSessioni:
    oggi = oggi or datetime.now(TZ).date()
    with db_context._connect(settings) as conn, conn.cursor() as cur:
        righe = leggi_righe(cur)
    return assegna(righe, oggi, giorni, n_sessioni, anticipo_max, ritardo_max)


# --- testo (terminale) ---------------------------------------------------------

def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def _data(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}"


def testo(p: PianoSessioni) -> list[str]:
    nomi = " e ".join(NOMI_GIORNO[g - 1] for g in p.giorni)
    out = [f"== PIANO SEMINE - sessioni {nomi} (oggi {NOMI_GIORNO[p.oggi.weekday()]} {p.oggi.isoformat()}) - SOLA LETTURA"]
    if not p.sessioni:
        out.append("\nNessuna semina da fare nelle sessioni: nessuna riga del piano e' ancora da avviare in tempo utile.")
    for s in p.sessioni:
        tot = ", ".join(f"{_n(q)} {u}" for u, q in s.quantita_per_unita.items())
        out.append(f"\nSESSIONE {s.nome_giorno} {_data(s.data)}{'  (OGGI)' if s.data == p.oggi else ''}"
                   f" - {len(s.varieta)} varieta', {tot}")
        for v in s.varieta:
            out.append(f"  {v.varieta}  {_n(v.quantita)} {v.unita}   ({_n(v.grammi.quantize(Decimal(1)))} g di seme)")
            for d in v.destinatari:
                extra = f"   <-- {'; '.join(d.note)}" if d.note else ""
                out.append(f"      {d.cliente}  {_n(d.quantita)}   consegna {_data(d.consegna)}  ({d.ordine}){extra}")
    if p.piu_avanti:
        out.append(f"\nPiu' avanti: altre {p.piu_avanti} righe, fino alla sessione del {_data(p.ultima_data_piu_avanti)}.")
    if p.da_verificare:
        out.append(f"\nDA VERIFICARE ({len(p.da_verificare)} ordini) - consegna troppo vicina per una semina nuova, NON nelle sessioni."
                   " Coperti da giacenza o semine in corso? Consegna da spostare?")
        for o in p.da_verificare:
            out.append(f"  {o.ordine}  {o.cliente}  consegna {_data(o.consegna)}  (piano in ritardo di {o.ritardo_giorni} gg): "
                       + ", ".join(o.voci))
    if p.scaduti:
        out.append(f"\nORDINI SCADUTI ({len(p.scaduti)}) - consegna prevista passata, ordine ancora aperto, NON nelle sessioni.")
        for o in p.scaduti:
            out.append(f"  {o.ordine}  {o.cliente}  prevista {_data(o.consegna)}  [{o.stato or '?'}]: " + ", ".join(o.voci))
        aperti = [o.ordine for o in p.scaduti if o.stato == "APERTO"]
        parziali = [o.ordine for o in p.scaduti if o.stato == "PARZIALMENTE_EVASO"]
        if parziali:
            out.append("  Se il residuo NON e' piu' dovuto (ordini PARZIALMENTE_EVASO, anteprima, senza --esegui non scrive):\n"
                       "    .venv/bin/python scripts/commissioning/2026-10-05_chiudi_residuo_ordini.py --ordini " + " ".join(parziali)
                       + " --solo-chiudibili\n    (chiude solo quelli chiudibili; gli altri, es. con righe mai consegnate, li elenca col motivo)")
        if aperti:
            out.append("  Se NON li consegni piu' (ordini APERTO, nessuna consegna: si annullano; anteprima, senza --esegui non scrive):\n"
                       "    .venv/bin/python scripts/commissioning/2026-10-07_modifica_ordine.py annulla " + " ".join(aperti)
                       + ' --motivo "Ordine scaduto non piu\' dovuto"')
    return out


def _ordine_dict(o: OrdineDaVerificare) -> dict:
    return {"ordine": o.ordine, "cliente": o.cliente, "consegna": o.consegna.isoformat(),
            "ritardo_giorni": o.ritardo_giorni, "voci": list(o.voci), "stato": o.stato}


def a_dizionario(p: PianoSessioni) -> dict:
    return {
        "oggi": p.oggi.isoformat(), "giorni": [NOMI_GIORNO[g - 1] for g in p.giorni],
        "piu_avanti": p.piu_avanti,
        "ultima_data_piu_avanti": p.ultima_data_piu_avanti.isoformat() if p.ultima_data_piu_avanti else None,
        "scaduti": [_ordine_dict(o) for o in p.scaduti],
        "da_verificare": [_ordine_dict(o) for o in p.da_verificare],
        "sessioni": [{
            "data": s.data.isoformat(), "giorno": s.nome_giorno, "oggi": s.data == p.oggi,
            "totali": {u: _n(q) for u, q in s.quantita_per_unita.items()},
            "varieta": [{
                "varieta": v.varieta, "unita": v.unita, "quantita": _n(v.quantita),
                "grammi": _n(v.grammi.quantize(Decimal(1))),
                "destinatari": [{
                    "cliente": d.cliente, "quantita": _n(d.quantita), "consegna": d.consegna.isoformat(),
                    "ordine": d.ordine, "note": list(d.note),
                } for d in v.destinatari],
            } for v in s.varieta],
        } for s in p.sessioni],
    }
