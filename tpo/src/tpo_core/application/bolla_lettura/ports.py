"""Porta del reader a sola lettura BOLLA DI CONSEGNA."""

from typing import Protocol

from .models import Bolla, RichiediBolla


class BollaLetturaReader(Protocol):
    def bolla(self, query: RichiediBolla) -> Bolla:
        """Legge la CONSEGNA con righe e provenienza di lotto. Sola lettura."""
        ...
