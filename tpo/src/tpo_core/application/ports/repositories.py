"""Porte dei Repository necessarie ai casi d'uso applicativi."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ...domain.entities.programma_fornitura import ProgrammaFornitura

if TYPE_CHECKING:
    from ..scheduling.models import ScheduledOrderRecord


class ProgrammaFornituraRepository(Protocol):
    """Accesso in lettura ai PROGRAMMI_FORNITURA per lo Scheduling."""

    def list_for_scheduling(self) -> tuple[ProgrammaFornitura, ...]:
        """Restituisce i programmi rilevanti senza applicare filtri di dominio."""
        ...


class OrdineRepository(Protocol):
    """Accesso ai record applicativi degli ORDINI generati dallo Scheduling."""

    def list_scheduled_orders(self) -> tuple[ScheduledOrderRecord, ...]:
        """Restituisce i record necessari alla verifica di idempotenza."""
        ...

    def add_scheduled_orders(
        self,
        records: tuple[ScheduledOrderRecord, ...],
    ) -> None:
        """Aggiunge i nuovi record conservandone ordine e metadati."""
        ...
