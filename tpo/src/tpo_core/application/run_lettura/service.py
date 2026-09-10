"""Caso d'uso RUN/RUN_LOG (query a sola lettura)."""

from .errors import InvalidRunLetturaQueryError
from .models import ElencoRun, RichiediElencoRun, RichiediRunLog, RunLog
from .ports import RunLetturaReader


class RunLetturaService:
    def __init__(self, reader: RunLetturaReader) -> None:
        self._reader = reader

    def elenco(self, query: RichiediElencoRun) -> ElencoRun:
        if not isinstance(query, RichiediElencoRun):
            raise InvalidRunLetturaQueryError("query non valida.")
        return self._reader.elenco(query)

    def log(self, query: RichiediRunLog) -> RunLog:
        if not isinstance(query, RichiediRunLog):
            raise InvalidRunLetturaQueryError("query non valida.")
        return self._reader.log(query)
