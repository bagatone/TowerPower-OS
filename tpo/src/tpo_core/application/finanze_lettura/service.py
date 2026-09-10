"""Caso d'uso FINANZE (query a sola lettura: FATTURA/INCASSO/USCITA)."""

from .errors import InvalidFinanzeLetturaQueryError
from .models import (
    ElencoFatture, ElencoIncassi, ElencoUscite,
    RichiediElencoFatture, RichiediElencoIncassi, RichiediElencoUscite,
)
from .ports import FinanzeLetturaReader


class FinanzeLetturaService:
    def __init__(self, reader: FinanzeLetturaReader) -> None:
        self._reader = reader

    def fatture(self, query: RichiediElencoFatture) -> ElencoFatture:
        if not isinstance(query, RichiediElencoFatture):
            raise InvalidFinanzeLetturaQueryError("query non valida.")
        return self._reader.fatture(query)

    def incassi(self, query: RichiediElencoIncassi) -> ElencoIncassi:
        if not isinstance(query, RichiediElencoIncassi):
            raise InvalidFinanzeLetturaQueryError("query non valida.")
        return self._reader.incassi(query)

    def uscite(self, query: RichiediElencoUscite) -> ElencoUscite:
        if not isinstance(query, RichiediElencoUscite):
            raise InvalidFinanzeLetturaQueryError("query non valida.")
        return self._reader.uscite(query)
