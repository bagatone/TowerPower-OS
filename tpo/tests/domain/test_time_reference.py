from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.domain.errors import InvalidTimeReferenceError
from src.tpo_core.domain.time_reference import (
    OFFICIAL_TIMEZONE,
    OFFICIAL_TIMEZONE_NAME,
    CurrentSystemDate,
)


def test_official_timezone_is_atlantic_canary() -> None:
    assert OFFICIAL_TIMEZONE_NAME == "Atlantic/Canary"
    assert OFFICIAL_TIMEZONE.key == "Atlantic/Canary"


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(InvalidTimeReferenceError):
        CurrentSystemDate(datetime(2026, 8, 1, 12, 0))


def test_datetime_from_another_timezone_is_converted_deterministically() -> None:
    reference = CurrentSystemDate(datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc))
    assert reference.datetime == datetime(2026, 1, 15, 12, 0, tzinfo=OFFICIAL_TIMEZONE)
    assert reference.date.isoformat() == "2026-01-15"
    assert reference.time.hour == 12


def test_summer_timezone_conversion_is_deterministic() -> None:
    source = datetime(2026, 8, 1, 12, 0, tzinfo=ZoneInfo("Europe/Rome"))
    reference = CurrentSystemDate(source)
    assert reference.datetime.isoformat() == "2026-08-01T11:00:00+01:00"


def test_current_system_date_uses_only_the_supplied_reference() -> None:
    supplied = datetime(2030, 5, 6, 7, 8, 9, tzinfo=timezone.utc)
    assert CurrentSystemDate(supplied).datetime.isoformat() == "2030-05-06T08:08:09+01:00"


def test_current_system_date_is_immutable() -> None:
    reference = CurrentSystemDate(datetime(2026, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(FrozenInstanceError):
        reference.value = datetime(2027, 1, 1, tzinfo=timezone.utc)
