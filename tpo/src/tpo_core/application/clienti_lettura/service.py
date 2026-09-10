"""Caso d'uso CLIENTI (query a sola lettura)."""

from .errors import InvalidClientiLetturaQueryError
from .models import Cliente, ElencoClienti, RichiediCliente, RichiediElencoClienti
from .ports import ClientiLetturaReader


class ClientiLetturaService:
    def __init__(self, reader: ClientiLetturaReader) -> None:
        self._reader = reader

    def cliente(self, query: RichiediCliente) -> Cliente:
        if not isinstance(query, RichiediCliente):
            raise InvalidClientiLetturaQueryError("query non valida.")
        return self._reader.cliente(query)

    def elenco(self, query: RichiediElencoClienti) -> ElencoClienti:
        if not isinstance(query, RichiediElencoClienti):
            raise InvalidClientiLetturaQueryError("query non valida.")
        return self._reader.elenco(query)
