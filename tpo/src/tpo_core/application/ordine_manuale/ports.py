"""Porta dell'unico writer ORDINE_MANUALE."""

from typing import Protocol

from .models import RegistraOrdineManuale, RegistraOrdineManualeResult


class OrdineManualeWriter(Protocol):
    def registra(self, command: RegistraOrdineManuale) -> RegistraOrdineManualeResult:
        """Pubblica un ORDINE MANUALE con le sue righe, identita', audit e
        idempotenza nello stesso commit."""
        ...
