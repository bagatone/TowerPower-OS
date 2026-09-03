"""Comandi e risultati immutabili del commissioning SEMENTE_IMPIEGO."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib

from ...domain.identifiers import ActorId, ProtocolloVersioneId
from ...domain.states import SementeRaccomandazione
from .errors import InvalidSementeImpiegoCommandError


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidSementeImpiegoCommandError(f"{name} deve essere testo normalizzato non vuoto.")


def _optional_text(name: str, value: object) -> None:
    if value is not None:
        _text(name, value)


@dataclass(frozen=True)
class SementeImpiegoCommissioningAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidSementeImpiegoCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class CommissionSementeImpiego:
    fornitore: str
    referenza_commerciale: str
    protocol_version_public_id: ProtocolloVersioneId
    raccomandazione: SementeRaccomandazione
    rating: Decimal | None
    motivazione: str | None
    authority: SementeImpiegoCommissioningAuthority

    def __post_init__(self) -> None:
        _text("fornitore", self.fornitore)
        _text("referenza_commerciale", self.referenza_commerciale)
        if not isinstance(self.protocol_version_public_id, ProtocolloVersioneId):
            raise InvalidSementeImpiegoCommandError("protocol_version_public_id non valido.")
        if not isinstance(self.raccomandazione, SementeRaccomandazione):
            raise InvalidSementeImpiegoCommandError("raccomandazione non valida.")
        if self.rating is not None:
            if isinstance(self.rating, bool) or not isinstance(self.rating, Decimal):
                raise InvalidSementeImpiegoCommandError("rating deve essere Decimal.")
            if not self.rating.is_finite() or self.rating < 0 or self.rating > 100:
                raise InvalidSementeImpiegoCommandError("rating deve essere compreso tra 0 e 100.")
        _optional_text("motivazione", self.motivazione)
        if not isinstance(self.authority, SementeImpiegoCommissioningAuthority):
            raise InvalidSementeImpiegoCommandError("authority non valida.")

    @property
    def canonical_payload(self) -> str:
        values = (
            "SEMENTE-IMPIEGO-COMMISSIONING-V1", self.fornitore, self.referenza_commerciale,
            self.protocol_version_public_id.value, self.raccomandazione.value,
            _decimal(self.rating), self.motivazione,
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommissionSementeImpiegoResult:
    semente_impiego_id: int
    outcome: str
    fornitore: str
    referenza_commerciale: str
    varieta_public_id: str
    cultivar_denominazione: str
    uso_produttivo_denominazione: str
    raccomandazione: SementeRaccomandazione
    rating: Decimal | None
    motivazione: str | None
    ultima_revisione: date
    recorded_at: datetime

    def __post_init__(self) -> None:
        if (not isinstance(self.semente_impiego_id, int) or isinstance(self.semente_impiego_id, bool)
                or self.semente_impiego_id <= 0):
            raise InvalidSementeImpiegoCommandError("semente_impiego_id interno non valido.")


def _frame(value: str | None) -> str:
    if value is None:
        return "-1:"
    return f"{len(value.encode('utf-8'))}:{value}"


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = format(value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"
