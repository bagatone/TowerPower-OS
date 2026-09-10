"""Caso d'uso SEMENTE/LOTTO_SEME (query a sola lettura)."""

from .errors import InvalidSementeLetturaQueryError
from .models import (
    ElencoLotti, ElencoSementi, LottoSeme, RichiediElencoLotti,
    RichiediElencoSementi, RichiediLotto,
)
from .ports import SementeLetturaReader


class SementeLetturaService:
    def __init__(self, reader: SementeLetturaReader) -> None:
        self._reader = reader

    def elenco_sementi(self, query: RichiediElencoSementi) -> ElencoSementi:
        if not isinstance(query, RichiediElencoSementi):
            raise InvalidSementeLetturaQueryError("query non valida.")
        return self._reader.elenco_sementi(query)

    def lotto(self, query: RichiediLotto) -> LottoSeme:
        if not isinstance(query, RichiediLotto):
            raise InvalidSementeLetturaQueryError("query non valida.")
        return self._reader.lotto(query)

    def elenco_lotti(self, query: RichiediElencoLotti) -> ElencoLotti:
        if not isinstance(query, RichiediElencoLotti):
            raise InvalidSementeLetturaQueryError("query non valida.")
        return self._reader.elenco_lotti(query)
