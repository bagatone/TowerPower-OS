"""Porta del reader a sola lettura "Da seminare" (righe piano semina)."""

from typing import Protocol

from .models import ElencoDaSeminare, RichiediElencoDaSeminare


class PianificazioneSeminaLetturaReader(Protocol):
    def elenco(self, query: RichiediElencoDaSeminare) -> ElencoDaSeminare:
        """Legge le righe piano semina non ancora avviate della revisione
        corrente, ordinate per data/ora di semina piu' vicina. Sola lettura."""
        ...
