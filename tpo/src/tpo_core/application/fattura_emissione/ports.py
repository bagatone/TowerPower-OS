"""Porta dell'unico writer FATTURA_EMISSIONE."""

from typing import Protocol

from .models import EmitFattura, EmitFatturaResult


class FatturaEmissioneWriter(Protocol):
    def emit(self, command: EmitFattura) -> EmitFatturaResult:
        """Emette una FATTURA nel medesimo commit di numerazione e righe."""
        ...
