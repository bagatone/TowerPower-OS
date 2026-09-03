"""Comandi e risultati immutabili del commissioning SEMENTE."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib

from ...domain.identifiers import ActorId
from .errors import InvalidSementeCommandError

CONSTITUTIVE_FIELDS = ("fornitore", "referenza_commerciale")
METADATA_FIELDS = ("marca", "formato", "trattamento", "certificazioni")


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidSementeCommandError(f"{name} deve essere testo normalizzato non vuoto.")


def _optional_text(name: str, value: object) -> None:
    if value is not None:
        _text(name, value)


@dataclass(frozen=True)
class SementeCommissioningAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidSementeCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class CommissionSemente:
    fornitore: str
    referenza_commerciale: str
    marca: str | None
    formato: str | None
    trattamento: str | None
    certificazioni: str | None
    authority: SementeCommissioningAuthority

    def __post_init__(self) -> None:
        _text("fornitore", self.fornitore)
        _text("referenza_commerciale", self.referenza_commerciale)
        for name, value in (
            ("marca", self.marca), ("formato", self.formato),
            ("trattamento", self.trattamento), ("certificazioni", self.certificazioni),
        ):
            _optional_text(name, value)
        if not isinstance(self.authority, SementeCommissioningAuthority):
            raise InvalidSementeCommandError("authority non valida.")

    @property
    def canonical_payload(self) -> str:
        values = (
            "SEMENTE-COMMISSIONING-V1", self.fornitore, self.referenza_commerciale,
            self.marca, self.formato, self.trattamento, self.certificazioni,
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommissionSementeResult:
    semente_id: int
    outcome: str
    fornitore: str
    referenza_commerciale: str
    marca: str | None
    formato: str | None
    trattamento: str | None
    certificazioni: str | None
    attiva: bool
    recorded_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.semente_id, int) or isinstance(self.semente_id, bool) or self.semente_id <= 0:
            raise InvalidSementeCommandError("semente_id interno non valido.")


def _frame(value: str | None) -> str:
    if value is None:
        return "-1:"
    return f"{len(value.encode('utf-8'))}:{value}"
