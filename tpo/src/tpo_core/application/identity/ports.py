"""Porte specifiche per la persistenza delle sequenze identificative."""

from __future__ import annotations

from typing import Protocol, TypeVar

from ...domain.identifiers import PermanentId
from .models import (
    CommissionedIdentityRegistration,
    CommissionIdentityRegistration,
    IdentifierSequence,
)


IdentifierT = TypeVar("IdentifierT", bound=PermanentId)


class IdentifierSequenceRepository(Protocol):
    """Persistenza ottimistica di sequenze separate per tipo."""

    def get_sequence(self, identifier_type: type[IdentifierT]) -> IdentifierSequence:
        """Legge la sequenza persistente del tipo richiesto."""
        ...


class IdentityRegistrationCommissioningWriter(Protocol):
    """Writer append-only di una registrazione Identity esplicita."""

    def commission(
        self, command: CommissionIdentityRegistration,
    ) -> CommissionedIdentityRegistration:
        ...

    def compare_and_set(
        self,
        *,
        identifier_type: type[IdentifierT],
        expected_version: int,
        expected_next_value: int,
        new_next_value: int,
    ) -> bool:
        """Avanza atomicamente la sequenza soltanto se versione e valore coincidono."""
        ...
