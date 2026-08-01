"""Riferimento temporale ufficiale del Tower Power Operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from .errors import InvalidTimeReferenceError


OFFICIAL_TIMEZONE_NAME = "Atlantic/Canary"
OFFICIAL_TIMEZONE = ZoneInfo(OFFICIAL_TIMEZONE_NAME)


@dataclass(frozen=True)
class CurrentSystemDate:
    """Riferimento temporale ufficiale di una elaborazione."""

    value: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.value, datetime):
            raise InvalidTimeReferenceError("CURRENT_SYSTEM_DATE deve essere un datetime.")
        if self.value.tzinfo is None or self.value.utcoffset() is None:
            raise InvalidTimeReferenceError("CURRENT_SYSTEM_DATE deve includere il fuso orario.")
        object.__setattr__(self, "value", self.value.astimezone(OFFICIAL_TIMEZONE))

    @property
    def datetime(self) -> datetime:
        return self.value

    @property
    def date(self) -> date:
        return self.value.date()

    @property
    def time(self) -> time:
        return self.value.timetz()
