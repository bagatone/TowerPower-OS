"""PROMEMORIA DEGLI STADI e CONTROLLO ANOMALIE del diario (19/10/2026). SOLA LETTURA.

Due cose che oggi Matteo deve ricordarsi a mente o scoprire per caso:

1. PROMEMORIA: per ogni semina in coltivazione, dal protocollo si calcola QUANDO dovrebbe cambiare stadio.
   - AVVIATA/GERMINAZIONE (germinazione fisica): passa a LUCE a data_avvio + giorni di germinazione;
   - LUCE/CRESCITA (stesso processo): e' PRONTA a data della luce + giorni di crescita/luce.
   Si mostrano le semine "oggi", "domani" e "in ritardo" (la data prevista e' passata da poco).
   Sono previsioni dal protocollo: quello che conta e' lo stato fisico che Matteo dichiara; il diario NON cambia
   mai uno stato da solo.

2. ANOMALIE (cose che probabilmente non tornano nei dati):
   - semina ferma: in germinazione o in luce molto oltre la data prevista (stato probabilmente non aggiornato);
   - clienti con nome molto simile (es. Salvaje / Selvaje), con la segnalazione se hanno entrambi un programma attivo;
   - lotto di seme che basta per pochi SET (si guardano i lotti usati nell'ultimo mese).

Nessuna scrittura: la connessione e' aperta in sola lettura (guardia D del freeze OPERATIONAL_WEB_ADAPTER).
La funzione `componi` e' pura (nessun database): e' quella che si prova nei test.
"""
from __future__ import annotations

import difflib
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from . import db_context
from ..infrastructure.postgresql.settings import PostgreSQLSettings

TZ = ZoneInfo("Atlantic/Canary")
STADI_GERMINAZIONE = ("AVVIATA", "GERMINAZIONE")
STADI_LUCE = ("LUCE", "CRESCITA")
RITARDO_MAX_LUCE = 3          # giorni oltre la data prevista di passaggio a luce: poi e' "ferma"
RITARDO_MAX_PRONTA = 5        # giorni oltre la data prevista di pronta: poi e' "ferma" (finestra di raccolta di 5 giorni)
SIMILITUDINE_CLIENTI = 0.8
SEME_POCO_SET = 10            # sotto questi SET di seme residuo il lotto e' segnalato
SEME_ATTIVO_GIORNI = 30

SQL_SEMINE = """SELECT s.public_id, s.codice_tracciabilita, v.denominazione, s.stato::text, s.data_avvio,
       s.expected_useful_quantity, s.expected_useful_uom::text,
       pv.germinazione_giorni, pv.crescita_luce_giorni, pv.buffer_temporale_minuti,
       (SELECT min(e.effective_at) FROM tpo.semina_lifecycle_eventi e
         WHERE e.semina_id=s.id AND e.to_state='LUCE')
FROM tpo.semine s
JOIN tpo.varieta v ON v.id=s.varieta_id
LEFT JOIN tpo.protocollo_versioni pv ON pv.id=s.protocollo_versione_id
WHERE s.stato IN ('AVVIATA','GERMINAZIONE','LUCE','CRESCITA')
ORDER BY v.denominazione, s.data_avvio, s.public_id"""

SQL_CLIENTI = """SELECT cl.public_id, cl.denominazione,
       EXISTS(SELECT 1 FROM tpo.programmi_fornitura pf
              JOIN tpo.programmi_fornitura_versioni pv ON pv.programma_fornitura_id=pf.id
              WHERE pf.cliente_id=cl.id AND pv.valida_al IS NULL AND pv.voided_at IS NULL AND pv.stato='ATTIVO')
FROM tpo.clienti cl ORDER BY cl.public_id"""

SQL_LOTTI = """SELECT l.public_id, s.referenza_commerciale, l.quantita_residua,
       (SELECT pv.grammi_seme_per_set FROM tpo.semine se
          JOIN tpo.protocollo_versioni pv ON pv.id=se.protocollo_versione_id
         WHERE se.lotto_seme_id=l.id ORDER BY se.data_avvio DESC, se.id DESC LIMIT 1),
       (SELECT max(se.data_avvio) FROM tpo.semine se WHERE se.lotto_seme_id=l.id)
FROM tpo.lotti_seme l JOIN tpo.sementi s ON s.id=l.semente_id
WHERE l.unita_misura='GRAM' ORDER BY l.public_id"""


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower().strip()) if unicodedata.category(c) != "Mn")


def _n(value: Any) -> str:
    text = format(Decimal(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _locale(value: datetime) -> datetime:
    return value.astimezone(TZ) if value.tzinfo else value.replace(tzinfo=TZ)


def _breve(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}"


def _voce(codice, public_id, varieta, quantita, uom, data_prevista: date, oggi: date, azione: str) -> dict:
    sets = _n(quantita) if quantita is not None and uom == "SET" else None
    return {"semina": public_id, "codice": codice, "varieta": varieta, "set": sets, "azione": azione,
            "prevista": data_prevista.isoformat(), "giorni": (oggi - data_prevista).days}


def _stadi(semine: Sequence[Sequence[Any]], oggi: date) -> tuple[dict, list]:
    promemoria = {"oggi": [], "domani": [], "in_ritardo": []}
    anomalie: list[dict] = []
    for (pid, codice, varieta, stato, avvio, atteso, uom, germ, luce_giorni, _buffer, luce_at) in semine:
        if germ is None or luce_giorni is None:
            continue
        inizio = _locale(avvio).date()
        fine_germinazione = inizio + timedelta(days=int(germ))
        if stato in STADI_GERMINAZIONE:
            azione, prevista, limite = "luce", fine_germinazione, RITARDO_MAX_LUCE
            stato_testo = f"in germinazione dal {_breve(inizio)}"
        elif stato in STADI_LUCE:
            partenza = _locale(luce_at).date() if luce_at is not None else fine_germinazione
            azione, prevista, limite = "pronta", partenza + timedelta(days=int(luce_giorni)), RITARDO_MAX_PRONTA
            stato_testo = f"in luce dal {_breve(partenza)}"
        else:
            continue
        voce = _voce(codice, pid, varieta, atteso, uom, prevista, oggi, azione)
        ritardo = (oggi - prevista).days
        if ritardo > limite:
            cosa = "doveva passare a luce" if azione == "luce" else "doveva essere pronta"
            anomalie.append({
                "tipo": "semina_ferma", "azione": azione, "semina": pid, "codice": codice, "varieta": varieta,
                "testo": f"{varieta} {codice} ({pid}): {stato_testo}, {cosa} il {_breve(prevista)} "
                         f"({ritardo} giorni fa). Stato non aggiornato?"})
        elif ritardo > 0:
            promemoria["in_ritardo"].append(voce)
        elif ritardo == 0:
            promemoria["oggi"].append(voce)
        elif ritardo == -1:
            promemoria["domani"].append(voce)
    for chiave in promemoria:
        promemoria[chiave].sort(key=lambda v: (v["azione"], v["varieta"], v["semina"]))
    return promemoria, anomalie


def _clienti_simili(clienti: Sequence[Sequence[Any]]) -> list[dict]:
    voci = []
    for i, (id_a, nome_a, prog_a) in enumerate(clienti):
        for id_b, nome_b, prog_b in clienti[i + 1:]:
            a, b = _fold(nome_a), _fold(nome_b)
            if not a or not b:
                continue
            if difflib.SequenceMatcher(None, a, b).ratio() < SIMILITUDINE_CLIENTI:
                continue
            doppio = bool(prog_a and prog_b)
            testo = f"Clienti con nome molto simile: {nome_a} ({id_a}) e {nome_b} ({id_b})."
            if doppio:
                testo += " Hanno entrambi un programma attivo: se sono lo stesso cliente si generano ordini doppi."
            voci.append({"tipo": "clienti_simili", "clienti": [id_a, id_b], "doppio_programma": doppio, "testo": testo})
    return voci


def _lotti_in_esaurimento(lotti: Sequence[Sequence[Any]], oggi: date) -> list[dict]:
    voci = []
    for lse, referenza, residuo, gps, ultima in lotti:
        if gps is None or ultima is None or Decimal(gps) <= 0:
            continue
        if (oggi - _locale(ultima).date()).days > SEME_ATTIVO_GIORNI:
            continue
        set_possibili = (Decimal(residuo) / Decimal(gps)).to_integral_value(rounding="ROUND_FLOOR")
        if set_possibili < SEME_POCO_SET:
            voci.append({"tipo": "seme_poco", "lotto": lse, "set_possibili": _n(set_possibili),
                         "testo": f"Seme {referenza} ({lse}): residuo a sistema {_n(residuo)} g, bastano per circa "
                                  f"{_n(set_possibili)} SET."})
    return voci


def componi(semine: Sequence[Sequence[Any]], clienti: Sequence[Sequence[Any]], lotti: Sequence[Sequence[Any]],
            adesso: datetime | None = None) -> dict:
    adesso = adesso or datetime.now(TZ)
    oggi = _locale(adesso).date()
    promemoria, ferme = _stadi(semine, oggi)
    anomalie = ferme + _clienti_simili(clienti) + _lotti_in_esaurimento(lotti, oggi)
    return {"aggiornato": adesso.isoformat(), "oggi": oggi.isoformat(), "promemoria": promemoria,
            "anomalie": anomalie, "nota": "Previsioni dal protocollo: conta lo stato fisico che dichiari tu."}


def leggi(settings: PostgreSQLSettings, adesso: datetime | None = None) -> dict:
    with db_context._connect(settings) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(SQL_SEMINE)
            semine = cur.fetchall()
            cur.execute(SQL_CLIENTI)
            clienti = cur.fetchall()
            cur.execute(SQL_LOTTI)
            lotti = cur.fetchall()
    return componi(semine, clienti, lotti, adesso)


# ---- testo per l'avviso del mattino (nessun nome di cliente) ----

def righe_avviso(controlli: dict) -> list[str]:
    """Righe in piu' per l'avviso: cosa passa a luce / e' pronto oggi, e quante cose da controllare."""
    righe: list[str] = []
    voci = controlli["promemoria"]["oggi"] + controlli["promemoria"]["in_ritardo"]
    for azione, titolo in (("luce", "Passano a luce"), ("pronta", "Pronte da raccogliere")):
        per_varieta: dict[str, Decimal] = {}
        senza_set: set[str] = set()
        for v in voci:
            if v["azione"] != azione:
                continue
            if v["set"] is None:
                senza_set.add(v["varieta"])
            else:
                per_varieta[v["varieta"]] = per_varieta.get(v["varieta"], Decimal(0)) + Decimal(v["set"])
        elenco = [f"{nome} {_n(q).replace('.', ',')}" for nome, q in sorted(per_varieta.items())]
        elenco += [f"{nome} ?" for nome in sorted(senza_set - set(per_varieta))]
        if elenco:
            righe.append(f"{titolo}: {', '.join(elenco)}.")
    if controlli["anomalie"]:
        righe.append(f"Da controllare: {len(controlli['anomalie'])} (vedi Oggi).")
    return righe
