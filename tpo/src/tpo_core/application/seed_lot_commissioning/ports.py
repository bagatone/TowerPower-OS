from typing import Protocol

from .models import CommissionSeedLot, CommissionSeedLotResult


class SeedLotCommissioningWriter(Protocol):
    def commission(self, command: CommissionSeedLot) -> CommissionSeedLotResult: ...
