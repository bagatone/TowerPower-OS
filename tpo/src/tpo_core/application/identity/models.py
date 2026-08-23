"""Modelli immutabili della policy applicativa degli identificativi."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ...domain.identifiers import ActorId, PermanentId
from .errors import (
    InvalidIdentifierSequenceError,
    InvalidIdentityCommissioningCommandError,
)


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


@dataclass(frozen=True)
class CommissionIdentityRegistration:
    """Autorità esplicita necessaria ad aggiungere una sola sequenza tipizzata."""

    sequence_name: str
    permanent_id_type: type[PermanentId]
    prefix: str
    actor: ActorId

    def __post_init__(self) -> None:
        identifier_type = self.permanent_id_type
        if (
            not isinstance(identifier_type, type)
            or not issubclass(identifier_type, PermanentId)
            or identifier_type is PermanentId
        ):
            raise InvalidIdentityCommissioningCommandError(
                "permanent_id_type deve essere un tipo PermanentId concreto."
            )
        if (
            not isinstance(self.sequence_name, str)
            or not self.sequence_name
            or self.sequence_name != self.sequence_name.strip()
            or self.sequence_name != identifier_type.sequence_name
        ):
            raise InvalidIdentityCommissioningCommandError(
                "sequence_name non coincide con il tipo congelato."
            )
        if (
            not isinstance(self.prefix, str)
            or not self.prefix
            or self.prefix != self.prefix.strip()
            or self.prefix != identifier_type.prefix
        ):
            raise InvalidIdentityCommissioningCommandError(
                "prefix non coincide con il tipo congelato."
            )
        if not isinstance(self.actor, ActorId):
            raise InvalidIdentityCommissioningCommandError("actor non valido.")


@dataclass(frozen=True)
class CommissionedIdentityRegistration:
    """Registrazione persistita, nuova oppure riletta come replay compatibile."""

    command: CommissionIdentityRegistration
    sequence: IdentifierSequence
    commissioned_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.command, CommissionIdentityRegistration):
            raise InvalidIdentityCommissioningCommandError("command non valido.")
        if self.sequence.identifier_type != self.command.permanent_id_type.__name__:
            raise InvalidIdentityCommissioningCommandError("identifier_type persistito incoerente.")
        if self.sequence.prefix != self.command.prefix:
            raise InvalidIdentityCommissioningCommandError("prefix persistito incoerente.")
        if (
            not isinstance(self.commissioned_at, datetime)
            or self.commissioned_at.tzinfo is None
            or self.commissioned_at.utcoffset() is None
        ):
            raise InvalidIdentityCommissioningCommandError(
                "commissioned_at deve essere timezone-aware."
            )
