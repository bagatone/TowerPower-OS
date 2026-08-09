"""Costruzione Application del contesto operativo interno."""

from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from ...domain.identifiers import ActorId
from ..committer.context import CommitExecutionContext
from .models import RecognizedOperationalIdentity


OPERATIONAL_SCHEDULING_REASON = "operational scheduling"


class CorrelationIdGenerator(Protocol):
    """Genera correlation ID uniformi senza dipendere dal caller."""

    def generate(self) -> str:
        """Restituisce un nuovo correlation ID provider-neutral."""
        ...


class UuidCorrelationIdGenerator:
    """Generatore uniforme per il boundary operativo."""

    def generate(self) -> str:
        return str(uuid4())


class OperationalExecutionContextFactory:
    """Traduce l'identità riconosciuta nel contesto interno di commit."""

    def __init__(self, correlation_id_generator: CorrelationIdGenerator) -> None:
        self._correlation_id_generator = correlation_id_generator

    def create(
        self, operational_identity: RecognizedOperationalIdentity
    ) -> CommitExecutionContext:
        if not isinstance(operational_identity, RecognizedOperationalIdentity):
            raise ValueError(
                "operational_identity deve essere RecognizedOperationalIdentity."
            )
        return CommitExecutionContext(
            actor=ActorId(operational_identity.value),
            reason=OPERATIONAL_SCHEDULING_REASON,
            correlation_id=self._correlation_id_generator.generate(),
        )
