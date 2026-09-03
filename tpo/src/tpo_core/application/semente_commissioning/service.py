from .errors import InvalidSementeCommandError
from .models import CommissionSemente, CommissionSementeResult
from .ports import SementeCommissioningWriter


class SementeCommissioningService:
    def __init__(self, writer: SementeCommissioningWriter) -> None:
        self._writer = writer

    def commission(self, command: CommissionSemente) -> CommissionSementeResult:
        if not isinstance(command, CommissionSemente):
            raise InvalidSementeCommandError("command non valido.")
        return self._writer.commission(command)
