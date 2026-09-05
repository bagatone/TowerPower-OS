"""Contratti immutabili della query DISPONIBILITA_COMMERCIALE V1.

Autorità: docs/architecture/STOCK_DISPONIBILITA_COMMERCIALE_FREEZE.md. Query
a sola lettura (nessun comando/scrittura): PRENOTATO è calcolato dalle
RIGHE_ORDINE non ancora completamente evase (ORDINE in APERTO o
PARZIALMENTE_EVASO), VENDIBILE = DISPONIBILE (tpo.stock, invariato) -
PRENOTATO. Nessuna persistenza: tpo.stock non viene mai scritto da questa
query (Owner Decision D-STOCK-read-model).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...domain.identifiers import VarietaId
from .errors import InvalidDisponibilitaCommercialeQueryError


@dataclass(frozen=True)
class RichiediDisponibilitaCommerciale:
    varieta_id: VarietaId

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidDisponibilitaCommercialeQueryError("varieta_id non valido.")


@dataclass(frozen=True)
class DisponibilitaCommerciale:
    varieta_id: VarietaId
    unita_misura: str
    disponibile: Decimal
    prenotato: Decimal
    vendibile: Decimal
    integrita_allarme: bool

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidDisponibilitaCommercialeQueryError("varieta_id non valido.")
        if self.disponibile < 0 or self.prenotato < 0:
            raise InvalidDisponibilitaCommercialeQueryError(
                "disponibile e prenotato non possono essere negativi."
            )
        expected_vendibile = self.disponibile - self.prenotato
        if self.vendibile != expected_vendibile:
            raise InvalidDisponibilitaCommercialeQueryError(
                "vendibile deve essere esattamente disponibile - prenotato."
            )
        expected_allarme = self.vendibile < 0
        if self.integrita_allarme != expected_allarme:
            raise InvalidDisponibilitaCommercialeQueryError(
                "integrita_allarme deve riflettere esattamente vendibile < 0."
            )
