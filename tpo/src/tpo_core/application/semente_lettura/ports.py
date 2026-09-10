"""Porta del reader a sola lettura SEMENTE/LOTTO_SEME."""

from typing import Protocol

from .models import (
    ElencoLotti, ElencoSementi, LottoSeme, RichiediElencoLotti,
    RichiediElencoSementi, RichiediLotto,
)


class SementeLetturaReader(Protocol):
    def elenco_sementi(self, query: RichiediElencoSementi) -> ElencoSementi:
        """Legge il catalogo SEMENTI. Sola lettura."""
        ...

    def lotto(self, query: RichiediLotto) -> LottoSeme:
        """Legge un singolo LOTTO_SEME. Sola lettura."""
        ...

    def elenco_lotti(self, query: RichiediElencoLotti) -> ElencoLotti:
        """Legge l'elenco completo dei LOTTI_SEME. Sola lettura."""
        ...
