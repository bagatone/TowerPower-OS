"""Porta dell'unico writer MOVIMENTO_ARTICOLO."""

from typing import Protocol

from .models import RegistraMovimentoArticolo, RegistraMovimentoArticoloResult


class MovimentoArticoloWriter(Protocol):
    def registra(
        self, command: RegistraMovimentoArticolo
    ) -> RegistraMovimentoArticoloResult:
        """Pubblica un MOVIMENTO_MAGAZZINO su un ARTICOLO nel medesimo commit
        di allocazione identità, aggiornamento STOCK_ARTICOLI e audit."""
        ...
