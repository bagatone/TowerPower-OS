"""Porta temporale provider-neutral dell'Application Layer."""

from __future__ import annotations

from typing import Protocol

from ...domain.time_reference import CurrentSystemDate


class Clock(Protocol):
    """Fornisce un riferimento temporale timezone-aware."""

    def now(self) -> CurrentSystemDate: ...
