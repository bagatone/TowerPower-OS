from ..ports.clock import Clock
from .errors import InvalidAgronomicCommissioningCommandError
from .models import CommissionAgronomicProtocolCommand, CommissionedAgronomicProtocol
from .ports import AgronomicProtocolCommissioningWriter


class AgronomicProtocolCommissioningService:
    def __init__(self, *, writer: AgronomicProtocolCommissioningWriter, clock: Clock) -> None:
        self._writer = writer
        self._clock = clock

    def commission(self, command: CommissionAgronomicProtocolCommand) -> CommissionedAgronomicProtocol:
        if not isinstance(command, CommissionAgronomicProtocolCommand):
            raise InvalidAgronomicCommissioningCommandError("command non valido.")
        return self._writer.commission(CommissionedAgronomicProtocol(command, self._clock.now().datetime, ()))
