"""Value objects for the Semina Traceability Code Authority V1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from zoneinfo import ZoneInfo

from .errors import InvalidTraceabilityCodeError

CANARY = ZoneInfo("Atlantic/Canary")
_VARIETY = re.compile(r"^[A-Z]{3}$")
_SEMINA = re.compile(r"^([A-Z]{3})-([0-9]{2})([0-9]{2})-([A-Z])$")


@dataclass(frozen=True)
class VarietyTraceabilityCode:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _VARIETY.fullmatch(self.value):
            raise InvalidTraceabilityCodeError("Il codice VARIETA deve avere formato [A-Z]{3}.")


@dataclass(frozen=True)
class SeminaTraceabilityCode:
    value: str

    def __post_init__(self) -> None:
        match = _SEMINA.fullmatch(self.value) if isinstance(self.value, str) else None
        if not match:
            raise InvalidTraceabilityCodeError("Il codice SEMINA deve avere formato AAA-GGMM-L.")
        day, month = int(match.group(2)), int(match.group(3))
        try:
            datetime(2000, month, day)
        except ValueError as exc:
            raise InvalidTraceabilityCodeError("GGMM non e una data di calendario valida.") from exc

    @classmethod
    def build(cls, variety: VarietyTraceabilityCode, started_at: datetime,
              discriminator: str) -> "SeminaTraceabilityCode":
        if not isinstance(variety, VarietyTraceabilityCode):
            raise InvalidTraceabilityCodeError("Autorita codice VARIETA assente.")
        if not isinstance(started_at, datetime) or started_at.tzinfo is None:
            raise InvalidTraceabilityCodeError("Istante fisico timezone-aware richiesto.")
        if not isinstance(discriminator, str) or not re.fullmatch(r"[A-Z]", discriminator):
            raise InvalidTraceabilityCodeError("Discriminatore SEMINA non valido.")
        local = started_at.astimezone(CANARY)
        return cls(f"{variety.value}-{local:%d%m}-{discriminator}")
