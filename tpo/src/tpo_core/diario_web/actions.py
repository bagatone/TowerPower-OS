"""Costruzione e esecuzione delle due azioni in perimetro Fase 1 del
diario (vedi handoff/diario-governance-addendum.md): nuova semina
(`semina commission`) e cambio di stadio (`semina transition`).

Principio guida, identico a ogni script scritto a mano in questa
sessione: ogni identificativo/versione usato per SCRIVERE viene letto
dal database un istante prima di scrivere, mai riusato da una proposta
precedente. L'esecuzione vera passa sempre da `run_semina_command`, lo
stesso adapter CLI gia' scritto e testato -- questo file non duplica
nessuna regola di dominio, costruisce solo il `Namespace` che l'adapter
si aspetta (guardia D3/§5 del freeze: "nessuna nuova logica di
validazione lato web").
"""
from __future__ import annotations

import io
from argparse import Namespace
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..cli.semina import run_semina_command
from ..domain.states import SeminaState
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from . import db_context

ORDINE_STATI = [s.value for s in SeminaState]  # AVVIATA..CHIUSA, ordine dichiarato nel dominio
TZ_CANARIE = timezone(timedelta(hours=1))
TZ_LOCALE = ZoneInfo("Atlantic/Canary")      # ora legale compresa: serve per i giorni/ore dichiarati dall'utente
STADI_CON_PULSANTE = ("LUCE", "PRONTA_ALLA_RACCOLTA")   # cambi di stadio proponibili dai bottoni del Promemoria
ORA_PREDEFINITA_GIORNO_PASSATO = time(12, 0)


class PropostaAmbigua(Exception):
    """Sollevata quando la proposta richiederebbe di scegliere fra piu'
    candidati senza che l'utente abbia specificato quale -- non si sceglie
    mai da soli in questi casi, si chiede."""


class SeminaNonTrovata(Exception):
    pass


class SeminaOperazioneFallita(Exception):
    pass


@dataclass(frozen=True)
class PropostaCommission:
    varieta_public_id: str
    varieta_nome: str
    lotto_seme_public_id: str
    protocollo_versione_public_id: str
    grammi: str
    num_set: str
    physical_started_at: str
    origin: str
    residuo_dopo: str
    tipo: str = field(default="semina_commission", init=False)


@dataclass(frozen=True)
class PassoTransizione:
    stato: str
    istante: str | None = None          # ISO 8601 con fuso; None = "adesso" al momento dell'esecuzione


@dataclass(frozen=True)
class PropostaTransition:
    varieta_public_id: str
    semina_public_id: str
    varieta_nome: str
    stato_attuale: str
    passi: list[PassoTransizione]
    note: list[str] = field(default_factory=list)       # es. "ora non indicata: 12:00" (solo per l'anteprima)
    tipo: str = field(default="semina_transition", init=False)


def prepara_commission(
    settings: PostgreSQLSettings, varieta_public_id: str, varieta_nome: str,
    num_set: str, origin: str, physical_started_at: str | None,
) -> PropostaCommission:
    candidati = [c for c in db_context.candidati_lotto_protocollo(settings, varieta_public_id)
                 if c.anomalia is None]
    if not candidati:
        raise PropostaAmbigua(
            f"Nessun lotto seme pronto per {varieta_nome}: o non c'è nessun collegamento "
            f"semente->protocollo con seme disponibile, o l'unico lotto ha un'anomalia da "
            f"correggere prima (fuori dal perimetro del diario, va fatto come finora)."
        )
    if len(candidati) > 1:
        opzioni = ", ".join(f"{c.lotto_seme_public_id} ({c.fornitore})" for c in candidati)
        raise PropostaAmbigua(f"Più lotti possibili per {varieta_nome}: {opzioni}. Specifica quale.")
    c = candidati[0]
    grammi = c.grammi_seme_per_set * Decimal(str(num_set))
    if grammi > c.quantita_residua:
        raise PropostaAmbigua(
            f"Servirebbero {grammi}g ma il lotto {c.lotto_seme_public_id} ne ha solo "
            f"{c.quantita_residua} residui."
        )
    started_at = physical_started_at or datetime.now(TZ_CANARIE).replace(microsecond=0).isoformat()
    return PropostaCommission(
        varieta_public_id=varieta_public_id, varieta_nome=varieta_nome,
        lotto_seme_public_id=c.lotto_seme_public_id,
        protocollo_versione_public_id=c.protocollo_versione_public_id,
        grammi=str(grammi), num_set=str(num_set), physical_started_at=started_at,
        origin=origin, residuo_dopo=str(c.quantita_residua - grammi),
    )


def prepara_transition(
    settings: PostgreSQLSettings, varieta_public_id: str, varieta_nome: str, target_state: str,
    semina_public_id: str | None = None,
) -> PropostaTransition:
    if target_state not in ORDINE_STATI:
        raise PropostaAmbigua(f"Stato '{target_state}' non riconosciuto.")
    attive = db_context.semine_attive_per_varieta(settings, varieta_public_id)
    if not attive:
        raise SeminaNonTrovata(f"Nessuna semina attiva trovata per {varieta_nome}.")
    if semina_public_id:
        # L'utente ha indicato esplicitamente quale semina -- usa quella,
        # non serve chiedere anche se ce ne fossero altre attive per la
        # stessa varietà. Verificata comunque contro le semine attive lette
        # ora (mai un valore proposto in precedenza).
        semina = next((s for s in attive if s.public_id == semina_public_id), None)
        if semina is None:
            raise SeminaNonTrovata(
                f"{semina_public_id} non risulta una semina attiva di {varieta_nome} "
                f"(chiusa, di un'altra varietà, o codice sbagliato)."
            )
    elif len(attive) > 1:
        codici = ", ".join(s.public_id for s in attive)
        raise PropostaAmbigua(f"Più semine attive per {varieta_nome}: {codici}. Specifica quale.")
    else:
        semina = attive[0]
    idx_attuale = ORDINE_STATI.index(semina.stato)
    idx_target = ORDINE_STATI.index(target_state)
    if idx_target <= idx_attuale:
        raise PropostaAmbigua(f"{varieta_nome} ({semina.public_id}) è già a {semina.stato}.")
    passi = [PassoTransizione(stato=stato) for stato in ORDINE_STATI[idx_attuale + 1: idx_target + 1]]
    return PropostaTransition(
        varieta_public_id=varieta_public_id, semina_public_id=semina.public_id,
        varieta_nome=varieta_nome, stato_attuale=semina.stato, passi=passi,
    )


def istanti_passi(
    stati: list[str], avvio: datetime, ultimo_evento: datetime | None, giorno: date | None, ora: time | None,
    adesso: datetime,
) -> tuple[list[datetime], list[str]]:
    """Istante di ogni passo, rispettando le regole del dominio (strettamente crescenti, non prima dell'avvio) e
    quelle di buon senso (mai nel futuro). Funzione pura.

    - Il passaggio a GERMINAZIONE, quando non e' l'ultimo passo, e' amministrativo: alla data di avvio (come negli
      script fatti a mano). Gli altri passi finiscono all'istante dichiarato, a un minuto l'uno dall'altro.
    - Oggi senza ora = adesso. Giorno passato senza ora = 12:00 (orario non osservato)."""
    adesso = adesso.astimezone(TZ_LOCALE)
    oggi = adesso.date()
    giorno = giorno or oggi
    note: list[str] = []
    if giorno > oggi:
        raise PropostaAmbigua("La data scelta e' nel futuro: indica oggi o un giorno passato.")
    if ora is None:
        if giorno == oggi:
            t = adesso.replace(second=0, microsecond=0)
        else:
            ora = ORA_PREDEFINITA_GIORNO_PASSATO
            note.append(f"Ora non indicata: registro le {ora:%H:%M} (orario non osservato).")
    if ora is not None:
        t = datetime.combine(giorno, ora, tzinfo=TZ_LOCALE)
    if t > adesso:
        raise PropostaAmbigua("L'ora scelta e' nel futuro: indica un'ora gia' passata.")
    amministrativo = len(stati) > 1 and stati[0] == "GERMINAZIONE"
    reali = stati[1:] if amministrativo else stati
    reali_istanti = [t - timedelta(minutes=len(reali) - 1 - i) for i in range(len(reali))]
    minimo = max(x for x in (avvio, ultimo_evento) if x is not None)
    primo = reali_istanti[0]
    if primo < avvio or (ultimo_evento is not None and primo <= ultimo_evento) or (amministrativo and primo <= avvio):
        quando = minimo.astimezone(TZ_LOCALE)
        raise PropostaAmbigua(
            f"La data scelta e' troppo presto: l'ultimo passaggio registrato o l'avvio e' del {quando:%d/%m/%Y %H:%M}. "
            "Scegli un istante dopo.")
    istanti = ([avvio] if amministrativo else []) + reali_istanti
    return istanti, note


def prepara_transition_semina(
    settings: PostgreSQLSettings, semina_public_id: str, target_state: str,
    giorno: date | None = None, ora: time | None = None, adesso: datetime | None = None,
) -> PropostaTransition:
    """Cambio di stadio di UNA semina precisa (dal bottone del Promemoria), con giorno/ora dichiarati."""
    if target_state not in STADI_CON_PULSANTE:
        raise PropostaAmbigua(f"Da questo bottone si registrano solo i passaggi a {' o '.join(STADI_CON_PULSANTE)}.")
    semina = db_context.semina_per_public_id(settings, semina_public_id)
    if semina is None:
        raise SeminaNonTrovata(f"{semina_public_id} non esiste.")
    if semina.stato == "CHIUSA":
        raise PropostaAmbigua(f"{semina.varieta_nome} ({semina.public_id}) e' gia' CHIUSA.")
    idx_attuale, idx_target = ORDINE_STATI.index(semina.stato), ORDINE_STATI.index(target_state)
    if idx_target <= idx_attuale:
        raise PropostaAmbigua(f"{semina.varieta_nome} ({semina.public_id}) e' gia' a {semina.stato}.")
    stati = ORDINE_STATI[idx_attuale + 1: idx_target + 1]
    istanti, note = istanti_passi(stati, semina.data_avvio, semina.ultimo_evento, giorno, ora,
                                  adesso or datetime.now(TZ_LOCALE))
    return PropostaTransition(
        varieta_public_id=semina.varieta_public_id, semina_public_id=semina.public_id,
        varieta_nome=semina.varieta_nome, stato_attuale=semina.stato,
        passi=[PassoTransizione(stato=st, istante=i.astimezone(TZ_LOCALE).replace(microsecond=0).isoformat())
               for st, i in zip(stati, istanti)],
        note=note,
    )


def esegui_commission(settings: PostgreSQLSettings, proposta: PropostaCommission, actor: str) -> str:
    # Rilettura live difensiva: la versione del lotto seme potrebbe essere
    # cambiata fra la proposta e questa conferma (un altro movimento nel
    # frattempo) -- non ci si fida del valore proposto, si rilegge ora.
    candidati = db_context.candidati_lotto_protocollo(settings, proposta.varieta_public_id)
    aggiornato = next((c for c in candidati if c.lotto_seme_public_id == proposta.lotto_seme_public_id), None)
    if aggiornato is None:
        raise PropostaAmbigua(
            f"{proposta.lotto_seme_public_id} non è più un lotto valido per questa semina "
            f"(cambiato nel frattempo) -- rifai la richiesta."
        )
    marca = _ora_compatta()
    args = Namespace(
        semina_command="commission",
        seed_lot=proposta.lotto_seme_public_id,
        expected_seed_lot_version=aggiornato.lotto_seme_version,
        protocol_version=proposta.protocollo_versione_public_id,
        actual_seed_grams=proposta.grammi,
        physical_started_at=proposta.physical_started_at,
        origin=proposta.origin,
        planning_line=None, expected_planning_line_version=None, started_quantity_set=None,
        provenance='{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED",'
                   '"selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}',
        actor=actor,
        reason=f"Semina {proposta.varieta_nome} ({proposta.num_set} SET) registrata tramite il diario.",
        correlation_id=f"DIARIO-SEMINA-COMMISSION-{proposta.varieta_public_id}-{marca}",
        idempotency_key=f"diario-commission-{proposta.lotto_seme_public_id.lower()}-{marca}",
        confirm=True,
    )
    return _esegui(args)


def esegui_transition(settings: PostgreSQLSettings, proposta: PropostaTransition, actor: str) -> str:
    output = []
    for passo in proposta.passi:                  # prima di scrivere QUALSIASI passo: nessun istante nel futuro
        if passo.istante:
            try:
                quando = datetime.fromisoformat(passo.istante)
            except ValueError:
                quando = None
            if quando is None or quando.tzinfo is None or quando > datetime.now(timezone.utc) + timedelta(minutes=1):
                raise SeminaOperazioneFallita(f"Istante non valido o nel futuro per {passo.stato}: nulla registrato.")
    for passo in proposta.passi:
        # Rilettura live della versione corrente PRIMA di ogni singolo
        # passo (non solo prima del primo): dopo ogni transizione la
        # versione della semina cambia, e riusare un valore calcolato in
        # anticipo per l'intera sequenza sarebbe di nuovo un dato
        # "invecchiato", anche se di pochi secondi.
        attive = db_context.semine_attive_per_varieta(settings, proposta.varieta_public_id)
        semina = next((s for s in attive if s.public_id == proposta.semina_public_id), None)
        if semina is None:
            raise SeminaNonTrovata(
                f"{proposta.semina_public_id} non risulta più attiva (chiusa o modificata nel frattempo)."
            )
        effective_at = passo.istante or datetime.now(TZ_CANARIE).replace(microsecond=0).isoformat()
        dichiarata = (f" Data/ora dichiarata: {datetime.fromisoformat(passo.istante):%d/%m/%Y %H:%M}."
                      if passo.istante else "")
        marca = _ora_compatta()
        args = Namespace(
            semina_command="transition",
            semina=proposta.semina_public_id,
            expected_semina_version=semina.version,
            target_state=passo.stato,
            effective_at=effective_at,
            final_outcome=None,
            provenance='{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED"}',
            actor=actor,
            reason=f"Transizione a {passo.stato} per {proposta.varieta_nome} "
                   f"({proposta.semina_public_id}), registrata tramite il diario.{dichiarata}",
            correlation_id=f"DIARIO-SEMINA-TRANSITION-{proposta.semina_public_id}-{passo.stato}-{marca}",
            idempotency_key=f"diario-transition-{proposta.semina_public_id.lower()}-{passo.stato.lower()}-{marca}",
            confirm=True,
        )
        output.append(_esegui(args))
    return "\n\n".join(output)


def _esegui(args: Namespace) -> str:
    stdout, stderr = io.StringIO(), io.StringIO()
    exit_code = run_semina_command(args, stdout=stdout, stderr=stderr)
    testo = stdout.getvalue() or stderr.getvalue()
    if exit_code != 0:
        raise SeminaOperazioneFallita(testo.strip() or f"Fallito (codice {exit_code}).")
    return testo.strip()


def _ora_compatta() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
