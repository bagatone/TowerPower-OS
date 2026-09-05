"""Caso d'uso DISPONIBILITA_COMMERCIALE (query a sola lettura)."""

from .errors import InvalidDisponibilitaCommercialeQueryError
from .models import DisponibilitaCommerciale, RichiediDisponibilitaCommerciale
from .ports import DisponibilitaCommercialeReader


class DisponibilitaCommercialeService:
    def __init__(self, reader: DisponibilitaCommercialeReader) -> None:
        self._reader = reader

    def disponibilita(
        self, query: RichiediDisponibilitaCommerciale
    ) -> DisponibilitaCommerciale:
        if not isinstance(query, RichiediDisponibilitaCommerciale):
            raise InvalidDisponibilitaCommercialeQueryError("query non valida.")
        return self._reader.disponibilita(query)
