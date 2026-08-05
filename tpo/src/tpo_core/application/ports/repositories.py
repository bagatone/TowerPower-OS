"""Porte dei Repository necessarie ai casi d'uso applicativi."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ...domain.entities.programma_fornitura import ProgrammaFornitura

if TYPE_CHECKING:
    from ..scheduling.models import ScheduledOrderRecord
    from ..scheduling.provenance import VersionedProgrammaFornitura


class ProgrammaFornituraRepository(Protocol):
    """Accesso in lettura ai PROGRAMMI_FORNITURA per lo Scheduling."""

    def list_for_scheduling(self) -> tuple[ProgrammaFornitura, ...]:
        """Restituisce i programmi rilevanti senza applicare filtri di dominio."""
        ...


class VersionedProgrammaFornituraRepository(Protocol):
    """Sorgente autorevole di snapshot PROGRAMMA versionati e localizzati."""

    def list_versioned_for_scheduling(self) -> tuple[VersionedProgrammaFornitura, ...]: ...


class ScheduledOrderReadRepository(Protocol):
    """Accesso read-only agli ORDINI necessario allo Scheduling autorevole."""

    def list_scheduled_orders(self) -> tuple[ScheduledOrderRecord, ...]:
        """Restituisce i record necessari alla verifica di idempotenza."""
        ...



class OrdineRepository(ScheduledOrderReadRepository, Protocol):
    """Porta legacy; i nuovi runtime usano ``ScheduledOrderReadRepository``."""

    def add_scheduled_orders(self, records: tuple[ScheduledOrderRecord, ...]) -> None: ...
