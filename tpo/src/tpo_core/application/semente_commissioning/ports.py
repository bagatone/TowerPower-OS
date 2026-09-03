from typing import Protocol

from .models import CommissionSemente, CommissionSementeResult


class SementeCommissioningWriter(Protocol):
    def commission(self, command: CommissionSemente) -> CommissionSementeResult: ...
