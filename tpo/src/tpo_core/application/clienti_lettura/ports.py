"""Porta del reader a sola lettura CLIENTI."""

from typing import Protocol

from .models import Cliente, ElencoClienti, RichiediCliente, RichiediElencoClienti


class ClientiLetturaReader(Protocol):
    def cliente(self, query: RichiediCliente) -> Cliente:
        """Legge un singolo CLIENTE per identita' pubblica. Sola lettura."""
        ...

    def elenco(self, query: RichiediElencoClienti) -> ElencoClienti:
        """Legge l'elenco completo dei CLIENTI. Sola lettura."""
        ...
