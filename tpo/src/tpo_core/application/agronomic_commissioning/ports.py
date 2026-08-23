from typing import Protocol

from .models import CommissionedAgronomicProtocol


class AgronomicProtocolCommissioningWriter(Protocol):
    def commission(self, protocol: CommissionedAgronomicProtocol) -> CommissionedAgronomicProtocol: ...
