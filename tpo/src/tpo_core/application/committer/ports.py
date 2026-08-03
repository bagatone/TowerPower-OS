"""Porta del protocollo applicativo di preparazione del commit."""

from __future__ import annotations

from typing import Protocol

from .models import CommitRequest


class CommitRepository(Protocol):
    """Confine che registra esclusivamente la preparazione richiesta."""

    def prepare_commit(self, request: CommitRequest) -> None:
        """Prepara il commit senza applicare effetti persistenti al target."""
        ...
