"""Porta dell'unico writer ARTICOLO_COMMISSIONING."""

from typing import Protocol

from .models import CommissionArticolo, CommissionArticoloResult


class ArticoloWriter(Protocol):
    def commission(self, command: CommissionArticolo) -> CommissionArticoloResult:
        """Commissiona un nuovo ARTICOLO nel medesimo commit di allocazione
        identità e audit."""
        ...
