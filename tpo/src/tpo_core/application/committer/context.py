"""Contesto provider-neutral dell'esecuzione di un commit."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.identifiers import ActorId
from .errors import InvalidCommitRequestError


def _required_text(name: str, value: str) -> None:
    if not isinstance(value, str):
        raise InvalidCommitRequestError(f"{name} deve essere una stringa.")
    if not value or not value.strip():
        raise InvalidCommitRequestError(f"{name} non può essere vuoto.")
    if value != value.strip():
        raise InvalidCommitRequestError(
            f"{name} non accetta whitespace iniziale o finale."
        )


@dataclass(frozen=True)
class CommitExecutionContext:
    """Dichiara esplicitamente chi richiede il commit e perché."""

    actor: ActorId
    reason: str
    correlation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidCommitRequestError("actor deve essere un ActorId.")
        _required_text("reason", self.reason)
        _required_text("correlation_id", self.correlation_id)
