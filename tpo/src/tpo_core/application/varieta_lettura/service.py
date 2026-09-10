"""Caso d'uso VARIETA/LISTINO_VARIETA (query a sola lettura)."""

from .errors import InvalidVarietaLetturaQueryError
from .models import ElencoVarieta, RichiediElencoVarieta, RichiediVarieta, Varieta
from .ports import VarietaLetturaReader


class VarietaLetturaService:
    def __init__(self, reader: VarietaLetturaReader) -> None:
        self._reader = reader

    def varieta(self, query: RichiediVarieta) -> Varieta:
        if not isinstance(query, RichiediVarieta):
            raise InvalidVarietaLetturaQueryError("query non valida.")
        return self._reader.varieta(query)

    def elenco(self, query: RichiediElencoVarieta) -> ElencoVarieta:
        if not isinstance(query, RichiediElencoVarieta):
            raise InvalidVarietaLetturaQueryError("query non valida.")
        return self._reader.elenco(query)
