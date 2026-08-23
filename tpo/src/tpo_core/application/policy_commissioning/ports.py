"""Port owned by Production Planning policy commissioning."""

from typing import Protocol

from .models import CommissionedProductionPlanningPolicy


class ProductionPlanningPolicyCommissioningWriter(Protocol):
    def commission(
        self, policy: CommissionedProductionPlanningPolicy,
    ) -> CommissionedProductionPlanningPolicy:
        """Insert or prove an exact compatible replay of one policy version."""
        ...
