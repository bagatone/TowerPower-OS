"""Porta del reader a sola lettura FINANZE (FATTURA/INCASSO/USCITA)."""

from typing import Protocol

from .models import (
    ElencoFatture, ElencoIncassi, ElencoUscite,
    RichiediElencoFatture, RichiediElencoIncassi, RichiediElencoUscite,
)


class FinanzeLetturaReader(Protocol):
    def fatture(self, query: RichiediElencoFatture) -> ElencoFatture:
        """Legge l'elenco completo delle FATTURE con le loro righe. Sola lettura."""
        ...

    def incassi(self, query: RichiediElencoIncassi) -> ElencoIncassi:
        """Legge l'elenco completo degli INCASSI. Sola lettura."""
        ...

    def uscite(self, query: RichiediElencoUscite) -> ElencoUscite:
        """Legge l'elenco completo delle USCITE. Sola lettura."""
        ...
