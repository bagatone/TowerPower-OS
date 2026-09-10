"""Porta del reader a sola lettura MAGAZZINO (STOCK/MOVIMENTO/ARTICOLO)."""

from typing import Protocol

from .models import (
    ElencoArticoli, ElencoMovimenti, ElencoStock,
    RichiediElencoArticoli, RichiediElencoMovimenti, RichiediElencoStock,
)


class MagazzinoLetturaReader(Protocol):
    def articoli(self, query: RichiediElencoArticoli) -> ElencoArticoli:
        """Legge l'elenco completo degli ARTICOLI. Sola lettura."""
        ...

    def stock(self, query: RichiediElencoStock) -> ElencoStock:
        """Legge l'elenco completo dello STOCK (VARIETA + ARTICOLI). Sola lettura."""
        ...

    def movimenti(self, query: RichiediElencoMovimenti) -> ElencoMovimenti:
        """Legge l'elenco completo dei MOVIMENTI_MAGAZZINO. Sola lettura."""
        ...
