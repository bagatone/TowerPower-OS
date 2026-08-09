"""Porta del protocollo applicativo di preparazione del commit."""

from __future__ import annotations

from typing import Protocol

from .models import CommitExecutionReceipt, CommitOutcomeUncertain, CommitRequest


class CommitRepository(Protocol):
    """Confine che registra esclusivamente la preparazione richiesta."""

    def prepare_commit(self, request: CommitRequest) -> None:
        """Prepara il commit senza applicare effetti persistenti al target."""
        ...

    def execute_commit(
        self,
        request: CommitRequest,
    ) -> CommitExecutionReceipt | CommitOutcomeUncertain:
        """Esegue un singolo commit e restituisce un outcome strutturato."""
        ...
