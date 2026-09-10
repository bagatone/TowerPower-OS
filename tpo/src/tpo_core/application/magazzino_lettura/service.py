"""Caso d'uso MAGAZZINO (query a sola lettura: STOCK/MOVIMENTO/ARTICOLO)."""

from .errors import InvalidMagazzinoLetturaQueryError
from .models import (
    ElencoArticoli, ElencoMovimenti, ElencoStock,
    RichiediElencoArticoli, RichiediElencoMovimenti, RichiediElencoStock,
)
from .ports import MagazzinoLetturaReader


class MagazzinoLetturaService:
    def __init__(self, reader: MagazzinoLetturaReader) -> None:
        self._reader = reader

    def articoli(self, query: RichiediElencoArticoli) -> ElencoArticoli:
        if not isinstance(query, RichiediElencoArticoli):
            raise InvalidMagazzinoLetturaQueryError("query non valida.")
        return self._reader.articoli(query)

    def stock(self, query: RichiediElencoStock) -> ElencoStock:
        if not isinstance(query, RichiediElencoStock):
            raise InvalidMagazzinoLetturaQueryError("query non valida.")
        return self._reader.stock(query)

    def movimenti(self, query: RichiediElencoMovimenti) -> ElencoMovimenti:
        if not isinstance(query, RichiediElencoMovimenti):
            raise InvalidMagazzinoLetturaQueryError("query non valida.")
        return self._reader.movimenti(query)
