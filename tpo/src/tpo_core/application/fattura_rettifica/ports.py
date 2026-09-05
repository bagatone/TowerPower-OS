"""Porta dell'unico writer FATTURA_RETTIFICA."""

from typing import Protocol

from .models import RectifyFattura, RectifyFatturaResult


class FatturaRettificaWriter(Protocol):
    def rectify(self, command: RectifyFattura) -> RectifyFatturaResult:
        """Emette una FATTURA rettificativa nel medesimo commit di numerazione e righe."""
        ...
