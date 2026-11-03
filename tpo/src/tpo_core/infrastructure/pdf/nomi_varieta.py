"""Nomi delle varieta' in SPAGNOLO per tutti i documenti stampati (bolle ed etichette).

Regola di Matteo (3/11/2026): i documenti destinati ai clienti sono sempre in spagnolo, anche i nomi delle varieta'.
A sistema alcune varieta' hanno il nome italiano: qui vengono tradotte SOLO in stampa (database e codici di
tracciabilita' non cambiano). Un nome non presente nella tabella esce com'e' (es. Afila, Rábano, Cilantro, Mizuna, Hinojo).
"""
from __future__ import annotations

NOMI_ES = {
    "acetosella": "Acedera",
    "basilico": "Albahaca",
    "bieta gialla": "Acelga amarilla",
    "bieta rossa": "Acelga roja",
    "broccolo": "Brócoli",
    "cavolo rosso": "Col roja",
    "girasole": "Girasol",
    "lenticchia": "Lenteja",
    "lupino": "Altramuz",
    "mais": "Maíz",
    "melissa": "Melisa",
    "nasturzio": "Capuchina",
    "prezzemolo": "Perejil",
    "rucola": "Rúcula",
    "senape": "Mostaza",
}


def nome_spagnolo(varieta: str) -> str:
    return NOMI_ES.get(varieta.strip().lower(), varieta)
