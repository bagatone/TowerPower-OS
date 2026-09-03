from typing import Protocol

from .models import CommissionSementeImpiego, CommissionSementeImpiegoResult


class SementeImpiegoCommissioningWriter(Protocol):
    def commission(self, command: CommissionSementeImpiego) -> CommissionSementeImpiegoResult: ...
