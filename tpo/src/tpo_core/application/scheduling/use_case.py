"""Caso d'uso di orchestrazione di una RUN dello Scheduling Engine."""

from __future__ import annotations

from ...domain.identifiers import IdGenerator, RunId
from ...domain.time_reference import CurrentSystemDate
from ..ports.repositories import (
    ScheduledOrderReadRepository,
    VersionedProgrammaFornituraRepository,
)
from .engine import SchedulingEngine
from .models import SchedulingRequest, SchedulingResult


class RunScheduling:
    """Orchestra Repository ed Engine senza duplicarne la logica."""

    def __init__(
        self,
        programmi_repository: VersionedProgrammaFornituraRepository,
        ordini_repository: ScheduledOrderReadRepository,
        id_generator: IdGenerator,
        scheduling_engine: SchedulingEngine,
    ) -> None:
        self._programmi_repository = programmi_repository
        self._ordini_repository = ordini_repository
        self._id_generator = id_generator
        self._scheduling_engine = scheduling_engine

    def execute(
        self,
        *,
        run_id: RunId,
        current_system_date: CurrentSystemDate,
        simulation: bool = False,
    ) -> SchedulingResult:
        if hasattr(self._programmi_repository, "list_versioned_for_scheduling"):
            programmi = self._programmi_repository.list_versioned_for_scheduling()
        elif simulation:
            programmi = self._programmi_repository.list_for_scheduling()
        else:
            raise TypeError(
                "Il runtime operativo richiede un repository PROGRAMMI versionato."
            )
        ordini_esistenti = self._ordini_repository.list_scheduled_orders()
        request = SchedulingRequest(
            run_id=run_id,
            current_system_date=current_system_date,
            programmi=programmi,
            ordini_esistenti=ordini_esistenti,
            id_generator=self._id_generator,
            simulation=simulation,
        )
        result = self._scheduling_engine.execute(request)
        return result
