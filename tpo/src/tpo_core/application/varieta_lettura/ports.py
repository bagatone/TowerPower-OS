"""Porta del reader a sola lettura VARIETA/LISTINO_VARIETA."""

from typing import Protocol

from .models import ElencoVarieta, RichiediElencoVarieta, RichiediVarieta, Varieta


class VarietaLetturaReader(Protocol):
    def varieta(self, query: RichiediVarieta) -> Varieta:
        """Legge una singola VARIETA (con prezzo/aliquota se presenti). Sola lettura."""
        ...

    def elenco(self, query: RichiediElencoVarieta) -> ElencoVarieta:
        """Legge l'elenco completo delle VARIETA. Sola lettura."""
        ...
