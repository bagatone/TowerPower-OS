"""Identificativi permanenti, tipizzati e semanticamente neutri."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar, Protocol, TypeVar

from .errors import InvalidIdentifierError


@dataclass(frozen=True)
class PermanentId:
    """Identificativo pubblico permanente appartenente a un solo tipo."""

    value: str
    prefix: ClassVar[str]

    def __post_init__(self) -> None:
        if type(self) is PermanentId:
            raise InvalidIdentifierError(
                "PermanentId è una classe base e non può essere istanziata direttamente."
            )
        if not isinstance(self.value, str) or not self.value:
            raise InvalidIdentifierError("L'identificativo deve essere una stringa non vuota.")

        pattern = rf"{re.escape(self.prefix)}-([0-9]{{6,}})"
        match = re.fullmatch(pattern, self.value)
        if match is None:
            raise InvalidIdentifierError(
                f"Identificativo non valido per {type(self).__name__}: {self.value!r}. "
                f"Formato atteso: {self.prefix}- seguito da almeno sei cifre."
            )
        if int(match.group(1)) <= 0:
            raise InvalidIdentifierError("La parte numerica dell'identificativo deve essere positiva.")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class VarietaId(PermanentId):
    prefix: ClassVar[str] = "VAR"


@dataclass(frozen=True)
class SeminaId(PermanentId):
    prefix: ClassVar[str] = "SEM"


@dataclass(frozen=True)
class RaccoltaId(PermanentId):
    prefix: ClassVar[str] = "RAC"


@dataclass(frozen=True)
class MovimentoId(PermanentId):
    prefix: ClassVar[str] = "MOV"


@dataclass(frozen=True)
class ProgrammaFornituraId(PermanentId):
    prefix: ClassVar[str] = "PF"


@dataclass(frozen=True)
class OrdineId(PermanentId):
    prefix: ClassVar[str] = "ORD"


@dataclass(frozen=True)
class ConsegnaId(PermanentId):
    prefix: ClassVar[str] = "CON"


@dataclass(frozen=True)
class RunId(PermanentId):
    prefix: ClassVar[str] = "RUN"


@dataclass(frozen=True)
class ClienteId(PermanentId):
    prefix: ClassVar[str] = "CLI"


IdentifierT = TypeVar("IdentifierT", bound=PermanentId)


class IdGenerator(Protocol):
    """Porta del dominio per la generazione di identificativi tipizzati."""

    def next_id(self, identifier_type: type[IdentifierT]) -> IdentifierT:
        """Restituisce il prossimo identificativo del tipo richiesto."""
        ...
