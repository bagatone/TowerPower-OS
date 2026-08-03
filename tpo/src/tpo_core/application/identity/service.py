"""Servizio applicativo puro per l'allocazione persistente degli ID."""

from __future__ import annotations

from typing import TypeVar

from ...domain.identifiers import PermanentId
from .errors import IdentifierSequenceConflictError, InvalidIdentifierSequenceError
from .models import AllocatedIdentifier, IdentifierSequence
from .ports import IdentifierSequenceRepository


IdentifierT = TypeVar("IdentifierT", bound=PermanentId)


class PersistentIdAllocator:
    """Alloca un ID tramite compare-and-set senza retry automatici."""

    def __init__(self, repository: IdentifierSequenceRepository) -> None:
        self._repository = repository

    def allocate(self, identifier_type: type[IdentifierT]) -> AllocatedIdentifier:
        if not isinstance(identifier_type, type) or not issubclass(identifier_type, PermanentId) or identifier_type is PermanentId:
            raise InvalidIdentifierSequenceError("È richiesto un sottotipo concreto di PermanentId.")

        before = self._repository.get_sequence(identifier_type)
        if before.identifier_type != identifier_type.__name__:
            raise InvalidIdentifierSequenceError("identifier_type della sequenza non coerente.")
        if before.prefix != identifier_type.prefix:
            raise InvalidIdentifierSequenceError("prefix della sequenza non coerente.")

        identifier = identifier_type(f"{before.prefix}-{before.next_value:06d}")
        advanced = self._repository.compare_and_set(
            identifier_type=identifier_type,
            expected_version=before.version,
            expected_next_value=before.next_value,
            new_next_value=before.next_value + 1,
        )
        if not advanced:
            raise IdentifierSequenceConflictError(
                f"Conflitto durante l'allocazione di {identifier_type.__name__}."
            )
        after = IdentifierSequence(
            identifier_type=before.identifier_type,
            prefix=before.prefix,
            next_value=before.next_value + 1,
            version=before.version + 1,
        )
        return AllocatedIdentifier(identifier, before, after)

    def next_id(self, identifier_type: type[IdentifierT]) -> IdentifierT:
        """Implementa la porta IdGenerator consumando permanentemente la sequenza."""
        return self.allocate(identifier_type).identifier
