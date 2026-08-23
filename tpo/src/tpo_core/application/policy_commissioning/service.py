"""Application service for explicit Production Planning policy commissioning."""

from ..ports.clock import Clock
from .errors import InvalidPolicyCommissioningCommandError
from .models import (
    CommissionProductionPlanningPolicyCommand,
    CommissionedProductionPlanningPolicy,
)
from .ports import ProductionPlanningPolicyCommissioningWriter


class ProductionPlanningPolicyCommissioningService:
    def __init__(
        self, *, writer: ProductionPlanningPolicyCommissioningWriter, clock: Clock,
    ) -> None:
        self._writer = writer
        self._clock = clock

    def commission(
        self, command: CommissionProductionPlanningPolicyCommand,
    ) -> CommissionedProductionPlanningPolicy:
        if not isinstance(command, CommissionProductionPlanningPolicyCommand):
            raise InvalidPolicyCommissioningCommandError("command non valido.")
        approved = CommissionedProductionPlanningPolicy(
            command=command,
            approved_at=self._clock.now().datetime,
        )
        return self._writer.commission(approved)
