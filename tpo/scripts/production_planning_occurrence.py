#!/usr/bin/env python3
"""Canonicalize a nominal automated Production Planning occurrence."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


OFFICIAL_TIMEZONE = "Atlantic/Canary"
OCCURRENCE_TIME = time(6, 30)


class InvalidNominalOccurrenceError(ValueError):
    pass


def canonical_business_at(
    nominal_date: date,
    *,
    local_time: time = OCCURRENCE_TIME,
    timezone_name: str = OFFICIAL_TIMEZONE,
) -> str:
    """Return one unambiguous, existent local occurrence with seconds."""

    if not isinstance(nominal_date, date) or isinstance(nominal_date, datetime):
        raise InvalidNominalOccurrenceError("nominal date invalid")
    if not isinstance(local_time, time) or local_time.tzinfo is not None:
        raise InvalidNominalOccurrenceError("nominal local time invalid")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, TypeError) as exc:
        raise InvalidNominalOccurrenceError("timezone unavailable") from exc
    naive = datetime.combine(nominal_date, local_time)
    candidates = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        roundtrip = candidate.astimezone(timezone.utc).astimezone(zone)
        if roundtrip.replace(tzinfo=None) == naive and roundtrip.fold == fold:
            candidates.append(candidate)
    unique = {item.utcoffset() for item in candidates}
    if len(unique) != 1:
        raise InvalidNominalOccurrenceError(
            "nominal local occurrence is ambiguous or nonexistent"
        )
    return candidates[0].isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    values = sys.argv[1:] if argv is None else argv
    if len(values) != 1:
        print("AUTOMATION_INPUT_INVALID", file=sys.stderr)
        return 2
    try:
        nominal_date = date.fromisoformat(values[0])
        print(canonical_business_at(nominal_date))
    except (InvalidNominalOccurrenceError, ValueError):
        print("AUTOMATION_INPUT_INVALID", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
