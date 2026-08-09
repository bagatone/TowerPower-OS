"""Adapter del clock di sistema per il runtime applicativo."""

from __future__ import annotations

from datetime import datetime, timezone

from ..domain.time_reference import CurrentSystemDate


class SystemClock:
    """Restituisce l'istante corrente in UTC senza side effect al costruttore."""

    def now(self) -> CurrentSystemDate:
        return CurrentSystemDate(datetime.now(timezone.utc))
