"""Contratti immutabili del Semina Commissioning Boundary V1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib

from ...domain.identifiers import (
    ActorId, LottoSemeId, ProtocolloVersioneId, RigaPianoSeminaId, SeminaId,
)
from ...domain.quantities import Quantity, UnitOfMeasure
from ...domain.traceability import SeminaTraceabilityCode
from .errors import (
    InvalidPhysicalStartError, InvalidSeminaCommandError, InvalidSeminaOriginError,
)

BASE_FACTS = frozenset({"physical_started_at", "actual_seed_grams", "selected_lse",
                        "selected_pv", "origin"})
PLANNED_FACT = "planned_started_quantity"


class SeminaOrigin(str, Enum):
    PIANO_PRODUZIONE = "PIANO_PRODUZIONE"
    ORDINE_CLIENTE = "ORDINE_CLIENTE"
    RIPRISTINO_STOCK = "RIPRISTINO_STOCK"


class SeminaFactSource(str, Enum):
    OWNER_AUTHORIZED = "OWNER_AUTHORIZED"
    LABEL_OR_PACKAGE = "LABEL_OR_PACKAGE"
    IMPORTED = "IMPORTED"


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidSeminaCommandError(f"{name} deve essere testo normalizzato non vuoto.")


def _version(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvalidSeminaCommandError(f"{name} deve essere un intero non negativo.")


def _exact_quantity(name: str, value: object, unit: UnitOfMeasure) -> None:
    if (not isinstance(value, Quantity) or value.unit is not unit or value.value <= 0
            or not value.value.is_finite() or value.value.as_tuple().exponent < -6):
        raise InvalidSeminaCommandError(f"{name} deve essere positiva, esatta e in {unit.value}.")


@dataclass(frozen=True)
class PlannedSeminaStart:
    planning_line_public_id: RigaPianoSeminaId
    expected_planning_line_version: int
    started_quantity: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.planning_line_public_id, RigaPianoSeminaId):
            raise InvalidSeminaCommandError("RPS non valida.")
        _version("expected_planning_line_version", self.expected_planning_line_version)
        _exact_quantity("started_quantity", self.started_quantity, UnitOfMeasure.SET)


@dataclass(frozen=True)
class SeminaCommissioningAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidSeminaCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class CommissionSemina:
    seed_lot_public_id: LottoSemeId
    expected_seed_lot_version: int
    protocol_version_public_id: ProtocolloVersioneId
    actual_seed_quantity: Quantity
    physical_started_at: datetime
    origin: SeminaOrigin
    planning_start: PlannedSeminaStart | None
    provenance: tuple[tuple[str, SeminaFactSource], ...]
    authority: SeminaCommissioningAuthority

    def __post_init__(self) -> None:
        if not isinstance(self.seed_lot_public_id, LottoSemeId):
            raise InvalidSeminaCommandError("LSE non valido.")
        if not isinstance(self.protocol_version_public_id, ProtocolloVersioneId):
            raise InvalidSeminaCommandError("PV non valido.")
        _version("expected_seed_lot_version", self.expected_seed_lot_version)
        _exact_quantity("actual_seed_quantity", self.actual_seed_quantity, UnitOfMeasure.GRAM)
        if (not isinstance(self.physical_started_at, datetime)
                or self.physical_started_at.tzinfo is None
                or self.physical_started_at.utcoffset() is None):
            raise InvalidPhysicalStartError("physical_started_at deve essere un istante esatto con timezone.")
        if not isinstance(self.origin, SeminaOrigin):
            raise InvalidSeminaOriginError("Origine SEMINA non valida.")
        planned = self.origin is SeminaOrigin.PIANO_PRODUZIONE
        if planned != isinstance(self.planning_start, PlannedSeminaStart):
            raise InvalidSeminaOriginError(
                "PIANO_PRODUZIONE richiede Planning start; le origini indipendenti lo vietano."
            )
        if not isinstance(self.authority, SeminaCommissioningAuthority):
            raise InvalidSeminaCommandError("authority non valida.")
        try:
            mapping = dict(self.provenance)
        except Exception as exc:
            raise InvalidSeminaCommandError("provenance non valida.") from exc
        required = BASE_FACTS | ({PLANNED_FACT} if planned else set())
        if len(mapping) != len(self.provenance) or set(mapping) != required:
            raise InvalidSeminaCommandError("provenance non coincide con i fatti fisici congelati.")
        if not all(isinstance(source, SeminaFactSource) for source in mapping.values()):
            raise InvalidSeminaCommandError("Fonte provenance non valida.")
        object.__setattr__(self, "physical_started_at", self.physical_started_at.astimezone(timezone.utc))
        object.__setattr__(self, "provenance", tuple(sorted(mapping.items())))

    @property
    def canonical_payload(self) -> str:
        planning = self.planning_start
        values = (
            "SEMINA-COMMISSIONING-V1", self.seed_lot_public_id.value,
            str(self.expected_seed_lot_version), self.protocol_version_public_id.value,
            _decimal(self.actual_seed_quantity.value),
            self.physical_started_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            self.origin.value, "true" if planning else "false",
            planning.planning_line_public_id.value if planning else None,
            str(planning.expected_planning_line_version) if planning else None,
            _decimal(planning.started_quantity.value) if planning else None,
            *(f"{field}={source.value}" for field, source in self.provenance),
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommissionSeminaResult:
    semina_id: SeminaId
    traceability_code: SeminaTraceabilityCode
    outcome: str
    state: str
    seed_lot_id: LottoSemeId
    seed_lot_version: int
    remaining_seed_quantity: Quantity
    planning_line_id: RigaPianoSeminaId | None
    planning_line_version: int | None
    recorded_at: datetime


def _frame(value: str | None) -> str:
    return "-1:" if value is None else f"{len(value.encode('utf-8'))}:{value}"


def _decimal(value: Decimal) -> str:
    normalized = format(value, "f").rstrip("0").rstrip(".")
    return normalized or "0"
