"""Porta dell'unico writer RETTIFICA_GIACENZA."""

from typing import Protocol

from .models import RettificaGiacenza, RettificaGiacenzaResult


class RettificaGiacenzaWriter(Protocol):
    def registra(self, command: RettificaGiacenza) -> RettificaGiacenzaResult:
        """Pubblica una rettifica in diminuzione di STOCK nel medesimo commit di
        allocazione identita', consumo di lotto e audit."""
        ...
