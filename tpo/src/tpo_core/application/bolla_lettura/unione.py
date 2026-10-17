"""Unione di piu' bolle dello stesso cliente in una sola (16/10/2026, richiesta di Matteo: Puipana CON-000020 + CON-000024).

Funzione pura sul read model: non legge ne' scrive nulla. Le righe restano quelle delle singole CONSEGNE
(nessuna quantita' viene sommata o cambiata): ognuna ricorda da quale CONSEGNA e da quale giorno viene.
Regola di onesta': le bolle si uniscono solo se sono dello stesso cliente, tutte CONSEGNATE e con lo stesso stato di
pagamento; altrimenti si rifiuta, senza indovinare.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Sequence

from .errors import UnioneBolleError
from .models import Bolla, PagamentoBolla


def _giorno(bolla: Bolla) -> date:
    return bolla.data_effettiva.date() if bolla.data_effettiva else bolla.data_prevista


def _chiave(bolla: Bolla) -> tuple[datetime, str]:
    quando = bolla.data_effettiva or datetime.combine(bolla.data_prevista, datetime.min.time(), tzinfo=timezone.utc)
    return (quando, bolla.consegna_id.value)


def _unico(valori: list[str | None]) -> str | None:
    distinti: list[str] = []
    for valore in valori:
        if valore and valore not in distinti:
            distinti.append(valore)
    return " / ".join(distinti) or None


def _pagamento(bolle: Sequence[Bolla]) -> PagamentoBolla | None:
    pagamenti = [b.pagamento for b in bolle]
    validi = [p for p in pagamenti if p is not None]
    if not validi:
        return None
    if len(validi) != len(pagamenti):
        raise UnioneBolleError(
            "alcune bolle risultano pagate e altre no: registra prima i pagamenti (o nessuno) e riprova.")
    primo = validi[0]
    if any((p.data_pagamento, p.metodo, p.storico) != (primo.data_pagamento, primo.metodo, primo.storico)
           for p in validi):
        raise UnioneBolleError("le bolle sono state pagate in date o con metodi diversi: non le unisco.")
    importi = [p.importo for p in validi]
    importo = sum((i for i in importi if i is not None), Decimal(0)) if all(i is not None for i in importi) else None
    return replace(primo, pagamento_id="+".join(p.pagamento_id for p in validi), importo=importo)


def unisci_bolle(bolle: Sequence[Bolla]) -> Bolla:
    if len(bolle) < 2:
        raise UnioneBolleError("servono almeno due bolle da unire.")
    codici = [b.consegna_id.value for b in bolle]
    if len(set(codici)) != len(codici):
        raise UnioneBolleError("la stessa CONSEGNA e' indicata piu' volte.")
    for b in bolle:
        if b.stato != "CONSEGNATA":
            raise UnioneBolleError(f"{b.consegna_id.value} e' in stato {b.stato}: si uniscono solo CONSEGNE CONSEGNATE.")
    if len({b.cliente_id for b in bolle}) != 1:
        raise UnioneBolleError("le bolle sono di clienti diversi: non le unisco.")
    ordinate = sorted(bolle, key=_chiave)
    righe = []
    for bolla in ordinate:
        for riga in bolla.righe:
            righe.append(replace(riga, posizione=len(righe) + 1, consegna_origine=bolla.consegna_id.value,
                                 data_consegna_origine=_giorno(bolla)))
    return replace(
        ordinate[-1],
        destinazione_fisica=_unico([b.destinazione_fisica for b in ordinate]),
        operatore=_unico([b.operatore for b in ordinate]),
        righe=tuple(righe),
        pagamento=_pagamento(ordinate),
        consegne_unite=tuple(b.consegna_id.value for b in ordinate),
    )
