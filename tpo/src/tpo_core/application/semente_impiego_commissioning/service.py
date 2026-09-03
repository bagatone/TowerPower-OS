from .errors import InvalidSementeImpiegoCommandError
from .models import CommissionSementeImpiego, CommissionSementeImpiegoResult
from .ports import SementeImpiegoCommissioningWriter


class SementeImpiegoCommissioningService:
    def __init__(self, writer: SementeImpiegoCommissioningWriter) -> None:
        self._writer = writer

    def commission(self, command: CommissionSementeImpiego) -> CommissionSementeImpiegoResult:
        if not isinstance(command, CommissionSementeImpiego):
            raise InvalidSementeImpiegoCommandError("command non valido.")
        return self._writer.commission(command)
