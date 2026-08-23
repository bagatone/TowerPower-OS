from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from ...domain.identifiers import ActorId, ProtocolloVersioneId, VarietaId
from .errors import InvalidAgronomicCommissioningCommandError


def _text(name: str, value: object, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidAgronomicCommissioningCommandError(f"{name} non valido.")


def _decimal(name: str, value: object, *, positive: bool = False) -> Decimal:
    if isinstance(value, (float, bool)):
        raise InvalidAgronomicCommissioningCommandError(f"{name} non accetta float o booleani.")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)  # type: ignore[arg-type]
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidAgronomicCommissioningCommandError(f"{name} deve essere Decimal.") from exc
    if not parsed.is_finite() or parsed.as_tuple().exponent < -6 or parsed < 0 or (positive and parsed <= 0):
        raise InvalidAgronomicCommissioningCommandError(f"{name} fuori dominio.")
    return parsed


@dataclass(frozen=True)
class CommissionAgronomicProtocolCommand:
    variety_id: VarietaId
    variety_name: str
    cultivar_name: str
    productive_use_code: str
    productive_use_name: str
    protocol_name: str
    protocol_version_id: ProtocolloVersioneId
    version: int
    valid_from: date
    valid_to: date | None
    hydration_hours: Decimal
    planned_sowing_time: time
    target_harvest_time: time
    germination_days: int
    light_growth_days: int
    seed_grams_per_set: Decimal
    expected_yield: Decimal
    production_granularity: Decimal
    harvest_min_lead_days: int
    harvest_max_lead_days: int
    temporal_buffer_minutes: int
    content: str
    motivation: str
    evidence: str | None
    provenance: str
    actor: ActorId
    reason: str
    correlation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.variety_id, VarietaId) or not isinstance(self.protocol_version_id, ProtocolloVersioneId):
            raise InvalidAgronomicCommissioningCommandError("Identity agronomica non valida.")
        for name in ("variety_name", "cultivar_name", "productive_use_code", "productive_use_name", "protocol_name", "content", "motivation", "provenance", "reason", "correlation_id"):
            _text(name, getattr(self, name))
        _text("evidence", self.evidence, optional=True)
        if not isinstance(self.actor, ActorId):
            raise InvalidAgronomicCommissioningCommandError("actor non valido.")
        if self.version != 1:
            raise InvalidAgronomicCommissioningCommandError("Il primo protocollo deve avere versione 1.")
        if not isinstance(self.valid_from, date) or isinstance(self.valid_from, datetime):
            raise InvalidAgronomicCommissioningCommandError("valid_from non valida.")
        if self.valid_to is not None and (not isinstance(self.valid_to, date) or isinstance(self.valid_to, datetime) or self.valid_to <= self.valid_from):
            raise InvalidAgronomicCommissioningCommandError("valid_to non valida.")
        for name in ("planned_sowing_time", "target_harvest_time"):
            if not isinstance(getattr(self, name), time):
                raise InvalidAgronomicCommissioningCommandError(f"{name} non valido.")
        for name in ("germination_days", "light_growth_days", "temporal_buffer_minutes"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise InvalidAgronomicCommissioningCommandError(f"{name} non valido.")
        if not isinstance(self.harvest_min_lead_days, int) or self.harvest_min_lead_days < 1 or self.harvest_max_lead_days < self.harvest_min_lead_days:
            raise InvalidAgronomicCommissioningCommandError("Harvest lead non valido.")
        for name, positive in (("hydration_hours", False), ("seed_grams_per_set", True), ("expected_yield", True), ("production_granularity", True)):
            object.__setattr__(self, name, _decimal(name, getattr(self, name), positive=positive))


@dataclass(frozen=True)
class CommissionedAgronomicProtocol:
    command: CommissionAgronomicProtocolCommand
    approved_at: datetime
    inserted_entities: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None:
            raise InvalidAgronomicCommissioningCommandError("approved_at deve essere timezone-aware.")
