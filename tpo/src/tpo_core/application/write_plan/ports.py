"""Porte applicative minime per la validazione del Write Plan."""

from __future__ import annotations

from typing import Protocol

from .models import WriteTargetSnapshot


class WritePlanValidationRepository(Protocol):
    """Lettura della vista logica necessaria alla validazione pre-commit."""

    def get_target_snapshot(self, *, target_name: str) -> WriteTargetSnapshot:
        """Restituisce target, schema e chiavi già esistenti."""
        ...
