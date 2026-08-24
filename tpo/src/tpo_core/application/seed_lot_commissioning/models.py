"""Comandi e risultati immutabili del commissioning LOTTO_SEME."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import hashlib

from ...domain.identifiers import ActorId, LottoSemeId
from ...domain.quantities import Quantity, UnitOfMeasure
from .errors import InvalidSeedLotCommandError, SeedLotQuantityInvalidError


FACT_FIELDS = (
    "seed_supplier", "seed_commercial_reference", "manufacturer_lot_number",
    "received_date", "expiry_date", "initial_quantity", "unit", "anomaly",
)


class SeedLotFactSource(str, Enum):
    OWNER_AUTHORIZED = "OWNER_AUTHORIZED"
    LABEL_OR_PACKAGE = "LABEL_OR_PACKAGE"
    IMPORTED = "IMPORTED"
    UNKNOWN = "UNKNOWN"


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidSeedLotCommandError(f"{name} deve essere testo normalizzato non vuoto.")


@dataclass(frozen=True)
class SeedLotCommissioningAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidSeedLotCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class CommissionSeedLot:
    seed_supplier: str
    seed_commercial_reference: str
    manufacturer_lot_number: str
    received_date: date
    expiry_date: date | None
    initial_quantity: Quantity
    anomaly: str | None
    provenance: tuple[tuple[str, SeedLotFactSource], ...]
    authority: SeedLotCommissioningAuthority

    def __post_init__(self) -> None:
        for name, value in (
            ("seed_supplier", self.seed_supplier),
            ("seed_commercial_reference", self.seed_commercial_reference),
            ("manufacturer_lot_number", self.manufacturer_lot_number),
        ):
            _text(name, value)
        if not isinstance(self.received_date, date):
            raise InvalidSeedLotCommandError("received_date esatta obbligatoria.")
        if self.expiry_date is not None:
            if not isinstance(self.expiry_date, date) or self.expiry_date < self.received_date:
                raise InvalidSeedLotCommandError("expiry_date non valida.")
        if (not isinstance(self.initial_quantity, Quantity)
                or self.initial_quantity.unit is not UnitOfMeasure.GRAM
                or self.initial_quantity.value <= 0):
            raise SeedLotQuantityInvalidError("initial_quantity deve essere positiva e in GRAM.")
        if self.anomaly is not None:
            _text("anomaly", self.anomaly)
        if not isinstance(self.authority, SeedLotCommissioningAuthority):
            raise InvalidSeedLotCommandError("authority non valida.")
        try:
            mapping = dict(self.provenance)
        except Exception as exc:
            raise InvalidSeedLotCommandError("provenance non valida.") from exc
        if len(mapping) != len(self.provenance) or set(mapping) != set(FACT_FIELDS):
            raise InvalidSeedLotCommandError("provenance deve classificare esattamente tutti i campi congelati.")
        for field, source in mapping.items():
            if not isinstance(source, SeedLotFactSource):
                raise InvalidSeedLotCommandError(f"provenance {field} non valida.")
            value = self.expiry_date if field == "expiry_date" else self.anomaly if field == "anomaly" else True
            if source is SeedLotFactSource.UNKNOWN and value is not None:
                raise InvalidSeedLotCommandError("UNKNOWN è ammesso solo per fatti opzionali assenti.")
            if source is not SeedLotFactSource.UNKNOWN and value is None:
                raise InvalidSeedLotCommandError("Un fatto opzionale assente richiede provenance UNKNOWN.")
        object.__setattr__(self, "provenance", tuple(sorted(mapping.items())))

    @property
    def canonical_payload(self) -> str:
        values = (
            "SEED-LOT-COMMISSIONING-V1", self.seed_supplier, self.seed_commercial_reference,
            self.manufacturer_lot_number, self.received_date.isoformat(),
            self.expiry_date.isoformat() if self.expiry_date else None,
            _decimal(self.initial_quantity.value), self.initial_quantity.unit.value,
            self.anomaly,
            *(f"{field}={source.value}" for field, source in self.provenance),
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommissionSeedLotResult:
    seed_lot_id: LottoSemeId
    outcome: str
    seed_supplier: str
    seed_commercial_reference: str
    manufacturer_lot_number: str
    initial_quantity: Quantity
    remaining_quantity: Quantity
    received_date: date
    expiry_date: date | None
    recorded_at: datetime


def _frame(value: str | None) -> str:
    if value is None:
        return "-1:"
    return f"{len(value.encode('utf-8'))}:{value}"


def _decimal(value: Decimal) -> str:
    normalized = format(value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"
