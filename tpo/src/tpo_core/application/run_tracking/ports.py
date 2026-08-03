"""Porta specifica per la persistenza della tracciabilità delle RUN."""

from __future__ import annotations

from typing import Protocol

from ...domain.identifiers import RunId
from .models import CompletedSchedulingRun, OpenSchedulingRun


class SchedulingRunRepository(Protocol):
    """Persistenza versionata di RUN aperte e concluse."""

    def add_open_run(self, run: OpenSchedulingRun) -> None:
        """Registra una RUN aperta rifiutando RunId duplicati."""
        ...

    def get(self, run_id: RunId) -> OpenSchedulingRun | CompletedSchedulingRun:
        """Restituisce la rappresentazione corrente della RUN."""
        ...

    def complete(
        self,
        *,
        run_id: RunId,
        expected_version: int,
        completed_run: CompletedSchedulingRun,
    ) -> bool:
        """Conclude la RUN soltanto se è ancora aperta alla versione attesa."""
        ...
