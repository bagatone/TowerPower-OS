from .errors import InvalidSeedLotCommandError
from .models import CommissionSeedLot, CommissionSeedLotResult
from .ports import SeedLotCommissioningWriter


class SeedLotCommissioningService:
    def __init__(self, writer: SeedLotCommissioningWriter) -> None:
        self._writer = writer

    def commission(self, command: CommissionSeedLot) -> CommissionSeedLotResult:
        if not isinstance(command, CommissionSeedLot):
            raise InvalidSeedLotCommandError("command non valido.")
        return self._writer.commission(command)
