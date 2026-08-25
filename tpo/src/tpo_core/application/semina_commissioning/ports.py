from typing import Protocol
from .models import CommissionSemina, CommissionSeminaResult


class SeminaCommissioningWriter(Protocol):
    def commission(self, command: CommissionSemina) -> CommissionSeminaResult: ...
