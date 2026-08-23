"""Immutable commands and outcomes for governed operational-data onboarding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ...domain.entities.programma_fornitura import ProgrammaFornitura
from ...domain.entities.varieta import Varieta
from ...domain.identifiers import ActorId, ClienteId
from .errors import InvalidOnboardingCommandError


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidOnboardingCommandError(f"{name} deve essere testo normalizzato non vuoto.")


@dataclass(frozen=True)
class OnboardingAuthority:
    actor: ActorId
    reason: str
    correlation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidOnboardingCommandError("actor non valido.")
        _text("reason", self.reason)
        _text("correlation_id", self.correlation_id)


@dataclass(frozen=True)
class CommissionCustomer:
    customer_id: ClienteId
    denomination: str
    authority: OnboardingAuthority

    def __post_init__(self) -> None:
        if not isinstance(self.customer_id, ClienteId):
            raise InvalidOnboardingCommandError("customer_id non valido.")
        _text("denomination", self.denomination)
        if not isinstance(self.authority, OnboardingAuthority):
            raise InvalidOnboardingCommandError("authority non valida.")


@dataclass(frozen=True)
class CommissionVariety:
    variety: Varieta
    authority: OnboardingAuthority

    def __post_init__(self) -> None:
        if not isinstance(self.variety, Varieta):
            raise InvalidOnboardingCommandError("variety non valida.")
        if not isinstance(self.authority, OnboardingAuthority):
            raise InvalidOnboardingCommandError("authority non valida.")


@dataclass(frozen=True)
class CommissionSupplyProgram:
    program: ProgrammaFornitura
    version: int
    valid_from: datetime
    authority: OnboardingAuthority

    def __post_init__(self) -> None:
        if not isinstance(self.program, ProgrammaFornitura):
            raise InvalidOnboardingCommandError("program non valido.")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version <= 0:
            raise InvalidOnboardingCommandError("version deve essere positiva.")
        if not isinstance(self.valid_from, datetime) or self.valid_from.tzinfo is None:
            raise InvalidOnboardingCommandError("valid_from deve essere timezone-aware.")
        if not isinstance(self.authority, OnboardingAuthority):
            raise InvalidOnboardingCommandError("authority non valida.")


@dataclass(frozen=True)
class OnboardingResult:
    entity_type: str
    public_id: str
    inserted: bool
