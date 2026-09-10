"""Porta del reader a sola lettura RUN/RUN_LOG."""

from typing import Protocol

from .models import ElencoRun, RichiediElencoRun, RichiediRunLog, RunLog


class RunLetturaReader(Protocol):
    def elenco(self, query: RichiediElencoRun) -> ElencoRun:
        """Legge l'elenco completo dei RUN con i loro messaggi. Sola lettura."""
        ...

    def log(self, query: RichiediRunLog) -> RunLog:
        """Legge il RUN_LOG di un singolo RUN. Sola lettura."""
        ...
