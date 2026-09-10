"""Porta del reader a sola lettura SEMINA/RACCOLTA."""

from typing import Protocol

from .models import ElencoSemine, RichiediElencoSemine, RichiediSemina, Semina


class SeminaRaccoltaLetturaReader(Protocol):
    def semina(self, query: RichiediSemina) -> Semina:
        """Legge una singola SEMINA con le sue RACCOLTE. Sola lettura."""
        ...

    def elenco(self, query: RichiediElencoSemine) -> ElencoSemine:
        """Legge l'elenco completo delle SEMINE con le rispettive RACCOLTE. Sola lettura."""
        ...
