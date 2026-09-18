"""Caso d'uso "Da seminare" (query a sola lettura)."""

from .errors import InvalidPianificazioneSeminaLetturaQueryError
from .models import ElencoDaSeminare, RichiediElencoDaSeminare
from .ports import PianificazioneSeminaLetturaReader


class PianificazioneSeminaLetturaService:
    def __init__(self, reader: PianificazioneSeminaLetturaReader) -> None:
        self._reader = reader

    def elenco(self, query: RichiediElencoDaSeminare) -> ElencoDaSeminare:
        if not isinstance(query, RichiediElencoDaSeminare):
            raise InvalidPianificazioneSeminaLetturaQueryError("query non valida.")
        return self._reader.elenco(query)
