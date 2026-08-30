"""Contratti immutabili del Raccolta Recording Boundary V1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib

from ...domain.identifiers import ActorId, RaccoltaId, SeminaId
from ...domain.quantities import Quantity, UnitOfMeasure
from ...domain.traceability import SeminaTraceabilityCode
from .errors import (
    InvalidRaccoltaCommandError, InvalidRaccoltaEffectiveAtError,
    InvalidRaccoltaQuantityError,
)


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidRaccoltaCommandError(f"{name} deve essere testo normalizzato non vuoto.")


@dataclass(frozen=True)
class RaccoltaAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidRaccoltaCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class RecordRaccolta:
    semina_id: SeminaId
    quantity: Quantity
    effective_at: datetime
    authority: RaccoltaAuthority
    notes: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.semina_id, SeminaId):
            raise InvalidRaccoltaCommandError("semina_id non valido.")
        if (not isinstance(self.quantity, Quantity)
                or self.quantity.unit is not UnitOfMeasure.SET
                or self.quantity.value <= 0
                or self.quantity.value.as_tuple().exponent < -6):
            raise InvalidRaccoltaQuantityError(
                "quantity deve essere positiva, esatta e in SET con massimo sei decimali."
            )
        if (not isinstance(self.effective_at, datetime)
                or self.effective_at.tzinfo is None
                or self.effective_at.utcoffset() is None):
            raise InvalidRaccoltaEffectiveAtError("effective_at deve essere aware.")
        if not isinstance(self.authority, RaccoltaAuthority):
            raise InvalidRaccoltaCommandError("authority non valida.")
        if self.notes is not None:
            _text("notes", self.notes)
        object.__setattr__(self, "effective_at", self.effective_at.astimezone(timezone.utc))

    @property
    def canonical_payload(self) -> str:
        values = (
            "RACCOLTA-RECORDING-V1", self.semina_id.value, _decimal(self.quantity.value),
            self.quantity.unit.value,
            self.effective_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            self.notes,
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RecordRaccoltaResult:
    raccolta_id: RaccoltaId
    semina_id: SeminaId
    traceability_code: SeminaTraceabilityCode
    quantity: Quantity
    effective_at: datetime
    recorded_at: datetime
    outcome: str


def _frame(value: str | None) -> str:
    return "-1:" if value is None else f"{len(value.encode('utf-8'))}:{value}"


def _decimal(value: Decimal) -> str:
    normalized = format(value, "f").rstrip("0").rstrip(".")
    return normalized or "0"
