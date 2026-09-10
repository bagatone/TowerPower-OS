"""Caso d'uso SEMINA/RACCOLTA (query a sola lettura)."""

from .errors import InvalidSeminaRaccoltaLetturaQueryError
from .models import ElencoSemine, RichiediElencoSemine, RichiediSemina, Semina
from .ports import SeminaRaccoltaLetturaReader


class SeminaRaccoltaLetturaService:
    def __init__(self, reader: SeminaRaccoltaLetturaReader) -> None:
        self._reader = reader

    def semina(self, query: RichiediSemina) -> Semina:
        if not isinstance(query, RichiediSemina):
            raise InvalidSeminaRaccoltaLetturaQueryError("query non valida.")
        return self._reader.semina(query)

    def elenco(self, query: RichiediElencoSemine) -> ElencoSemine:
        if not isinstance(query, RichiediElencoSemine):
            raise InvalidSeminaRaccoltaLetturaQueryError("query non valida.")
        return self._reader.elenco(query)
