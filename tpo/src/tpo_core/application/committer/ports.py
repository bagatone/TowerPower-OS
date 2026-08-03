"""Porta del protocollo applicativo di preparazione del commit."""

from __future__ import annotations

from typing import Protocol

from ...domain.time_reference import CurrentSystemDate
from .models import CommitExecutionReceipt, CommitRequest


class CommitRepository(Protocol):
    """Confine che registra esclusivamente la preparazione richiesta."""

    def prepare_commit(self, request: CommitRequest) -> None:
        """Prepara il commit senza applicare effetti persistenti al target."""
        ...

    def execute_commit(
        self,
        request: CommitRequest,
        completed_at: CurrentSystemDate,
    ) -> CommitExecutionReceipt:
        """Esegue un singolo commit e ne restituisce la ricevuta."""
        ...
