"""Modelli immutabili della policy applicativa degli identificativi."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.identifiers import PermanentId
from .errors import InvalidIdentifierSequenceError


@dataclass(frozen=True)
class IdentifierSequence:
    """Stato persistente di una sequenza tipizzata."""

    identifier_type: str
    prefix: str
    next_value: int
    version: int

    def __post_init__(self) -> None:
        if not isinstance(self.identifier_type, str) or not self.identifier_type:
            raise InvalidIdentifierSequenceError("identifier_type deve essere una stringa non vuota.")
        if not isinstance(self.prefix, str) or not self.prefix:
            raise InvalidIdentifierSequenceError("prefix deve essere una stringa non vuota.")
        if isinstance(self.next_value, bool) or not isinstance(self.next_value, int) or self.next_value <= 0:
            raise InvalidIdentifierSequenceError("next_value deve essere un intero positivo.")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 0:
            raise InvalidIdentifierSequenceError("version deve essere un intero non negativo.")


@dataclass(frozen=True)
class AllocatedIdentifier:
    """Identificativo allocato e transizione persistente che lo ha consumato."""

    identifier: PermanentId
    sequence_before: IdentifierSequence
    sequence_after: IdentifierSequence

    def __post_init__(self) -> None:
        if type(self.identifier) is PermanentId or not isinstance(self.identifier, PermanentId):
            raise InvalidIdentifierSequenceError("identifier deve essere un sottotipo concreto di PermanentId.")
        before = self.sequence_before
        after = self.sequence_after
        if before.identifier_type != type(self.identifier).__name__ or before.prefix != type(self.identifier).prefix:
            raise InvalidIdentifierSequenceError("La sequenza non corrisponde al tipo dell'identificativo.")
        if after.identifier_type != before.identifier_type or after.prefix != before.prefix:
            raise InvalidIdentifierSequenceError("La sequenza successiva deve conservare tipo e prefix.")
        if after.next_value != before.next_value + 1 or after.version != before.version + 1:
            raise InvalidIdentifierSequenceError("La transizione deve avanzare valore e versione di una unità.")
