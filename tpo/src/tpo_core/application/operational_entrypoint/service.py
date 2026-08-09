"""Boundary Application pubblico dell'Operational Scheduling."""

from __future__ import annotations

from ..operational_scheduling.models import OperationalSchedulingInput
from ..operational_scheduling.orchestrator import OperationalSchedulingOrchestrator
from .context import OperationalExecutionContextFactory
from .models import OperationalEntryPointResult, OperationalSchedulingIntent


class OperationalSchedulingEntryPoint:
    """Costruisce il contesto interno e delega una sola volta al runtime."""

    def __init__(
        self,
        context_factory: OperationalExecutionContextFactory,
        orchestrator: OperationalSchedulingOrchestrator,
    ) -> None:
        self._context_factory = context_factory
        self._orchestrator = orchestrator

    def execute(
        self, intent: OperationalSchedulingIntent
    ) -> OperationalEntryPointResult:
        if not isinstance(intent, OperationalSchedulingIntent):
            raise ValueError("intent deve essere OperationalSchedulingIntent.")
        execution_context = self._context_factory.create(
            intent.operational_identity
        )
        result = self._orchestrator.execute(
            OperationalSchedulingInput(
                current_system_date=intent.business_date,
                execution_context=execution_context,
            )
        )
        return OperationalEntryPointResult.from_operational_result(result)
