"""Bolla ed etichette di una consegna, scaricabili dal diario (5/11/2026, richiesta di Matteo: "il sistema il piu'
indipendente possibile", niente terminale per i documenti).

SOLA LETTURA: non scrive nulla sul database. Riusa gli stessi pezzi dei comandi `tpo bolla genera` e
`tpo etichetta genera` (stesso lettore, stesso PDF, stessi nomi spagnoli): nessuna regola duplicata qui.

- Bolla: con o senza prezzi (`senza_prezzi=True` per le prove gratuite: solo quel PDF, il listino non cambia).
- Etichette: foglio da 27 etichette 62x29 mm per A4 (default, come vuole Matteo) oppure una per pagina.
- Intestazione emittente (NIF, indirizzo): sul Mac sta in config/bolla_emittente.yaml (non in git); su Render nella
  variabile segreta DIARIO_BOLLA_EMITTENTE (stesso testo del file, oppure una riga per riga). Se non c'e' nessuna
  delle due, il PDF riporta solo "Tower Power", come il comando da terminale. Mai inventata.
- Le consegne recenti per scegliere quale scaricare (sola lettura).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..application.bolla_lettura.errors import BollaLetturaError, InvalidBollaLetturaQueryError
from ..application.bolla_lettura.models import RichiediBolla
from ..bootstrap import build_bolla_lettura_service
from ..cli.bolla import DEFAULT_EMITTENTE_FILE, _load_emittente, _slug
from ..cli.etichetta import _EtichetteError, costruisci_etichette
from ..domain.errors import InvalidIdentifierError
from ..domain.identifiers import ConsegnaId
from ..infrastructure.postgresql.errors import PostgreSQLError
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from . import db_context

LOCAL_TZ = ZoneInfo("Atlantic/Canary")
TZ_CANARIE = timezone(timedelta(hours=1))
ENV_EMITTENTE = "DIARIO_BOLLA_EMITTENTE"


class DocumentoNonPossibile(Exception):
    """Il documento non si puo' produrre (consegna inesistente o non consegnata, nessuna etichetta...)."""


@dataclass(frozen=True)
class Documento:
    contenuto: bytes
    nome_file: str


@dataclass(frozen=True)
class ConsegnaRecente:
    codice: str
    cliente: str
    data: str            # AAAA-MM-GG, giorno di consegna (fuso Canarie)
    voci: list[str]
    pagata: bool


_SQL_RECENTI = """
SELECT c.id, c.public_id, cl.denominazione, c.data_effettiva,
       EXISTS (SELECT 1 FROM tpo.pagamenti_consegna p
               WHERE p.consegna_id=c.id AND p.tipo='PAGAMENTO'
                 AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna a WHERE a.annulla_pagamento_id=p.id))
FROM tpo.consegne c JOIN tpo.clienti cl ON cl.id=c.cliente_id
WHERE c.stato='CONSEGNATA' AND c.data_effettiva >= now() - make_interval(days => %s)
ORDER BY c.data_effettiva DESC, c.public_id DESC"""
_SQL_VOCI = """
SELECT rc.consegna_id, v.denominazione, rc.quantita, rc.unita_misura::text
FROM tpo.righe_consegna rc JOIN tpo.varieta v ON v.id=rc.varieta_id
WHERE rc.consegna_id = ANY(%s) AND rc.rettifica_riga_consegna_id IS NULL
ORDER BY rc.consegna_id, rc.posizione"""


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def leggi_recenti(cur, giorni: int = 14) -> list[ConsegnaRecente]:
    cur.execute(_SQL_RECENTI, (giorni,))
    consegne = cur.fetchall()
    if not consegne:
        return []
    voci: dict[int, list[str]] = {}
    cur.execute(_SQL_VOCI, ([r[0] for r in consegne],))
    for cons_pk, nome, quantita, unita in cur.fetchall():
        voci.setdefault(cons_pk, []).append(f"{nome} {_n(quantita)} {unita}")
    return [ConsegnaRecente(codice, cliente, effettiva.astimezone(TZ_CANARIE).date().isoformat(),
                            voci.get(pk, []), bool(pagata))
            for pk, codice, cliente, effettiva, pagata in consegne]


def consegne_recenti(settings: PostgreSQLSettings, giorni: int = 14) -> list[ConsegnaRecente]:
    with db_context._connect(settings) as conn, conn.cursor() as cur:
        return leggi_recenti(cur, giorni)


def emittente() -> tuple[str, ...]:
    """Righe dell'intestazione: variabile segreta se c'e', altrimenti il file del Mac, altrimenti nessuna."""
    testo = os.environ.get(ENV_EMITTENTE, "").strip()
    if testo:
        import yaml

        try:
            caricato = yaml.safe_load(testo)
        except yaml.YAMLError:
            caricato = None
        if isinstance(caricato, dict) and isinstance(caricato.get("righe"), list) \
                and all(isinstance(r, str) for r in caricato["righe"]):
            return tuple(caricato["righe"])
        return tuple(r.strip() for r in testo.splitlines() if r.strip())
    return _load_emittente(DEFAULT_EMITTENTE_FILE, required=False)


def _leggi_bolla(settings: PostgreSQLSettings, codice: str):
    try:
        consegna_id = ConsegnaId(codice)
        return build_bolla_lettura_service(settings).bolla(RichiediBolla(consegna_id))
    except (ValueError, TypeError, InvalidIdentifierError, InvalidBollaLetturaQueryError) as exc:
        raise DocumentoNonPossibile(f"Codice consegna non valido: {exc}") from exc
    except BollaLetturaError as exc:
        raise DocumentoNonPossibile(str(exc)) from exc
    except PostgreSQLError as exc:
        raise DocumentoNonPossibile(f"Database non raggiungibile: {exc}") from exc


def _giorno(bolla):
    return (bolla.data_effettiva.astimezone(LOCAL_TZ).date() if bolla.data_effettiva else bolla.data_prevista)


def bolla_pdf(settings: PostgreSQLSettings, codice: str, *, senza_prezzi: bool = False) -> Documento:
    from ..infrastructure.pdf.bolla_pdf import render_bolla_pdf

    bolla = _leggi_bolla(settings, codice)
    if senza_prezzi:
        bolla = replace(bolla, righe=tuple(replace(r, prezzo_unitario=None) for r in bolla.righe))
    pdf = render_bolla_pdf(bolla, emittente=emittente(), generata_il=datetime.now(LOCAL_TZ))
    nome = f"bolla_{bolla.consegna_id.value}_{_slug(bolla.cliente_denominazione)}_{_giorno(bolla).isoformat()}.pdf"
    return Documento(pdf, nome)


def etichette_pdf(settings: PostgreSQLSettings, codice: str, *, foglio: bool = True) -> Documento:
    from ..infrastructure.pdf.etichette_pdf import render_etichette_foglio_pdf, render_etichette_pdf

    bolla = _leggi_bolla(settings, codice)
    try:
        etichette, _senza_origine = costruisci_etichette(bolla, 1)
    except _EtichetteError as exc:
        raise DocumentoNonPossibile(str(exc)) from exc
    if not etichette:
        raise DocumentoNonPossibile("Nessuna etichetta: la consegna non ha quantita' con origine tracciata.")
    pdf = render_etichette_foglio_pdf(etichette) if foglio else render_etichette_pdf(etichette)
    nome = (f"etichette_{bolla.consegna_id.value}_{_slug(bolla.cliente_denominazione)}_{_giorno(bolla).isoformat()}"
            f"{'_foglio' if foglio else ''}.pdf")
    return Documento(pdf, nome)
