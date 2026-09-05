"""Porta dell'unico writer MOVIMENTO_CARICO_RACCOLTA."""

from typing import Protocol

from .models import RegistraCaricoMagazzino, RegistraCaricoMagazzinoResult


class MovimentoCaricoWriter(Protocol):
    def registra(self, command: RegistraCaricoMagazzino) -> RegistraCaricoMagazzinoResult:
        """Pubblica un CARICO originato da una RACCOLTA nel medesimo commit di
        allocazione identità, aggiornamento STOCK e audit."""
        ...
