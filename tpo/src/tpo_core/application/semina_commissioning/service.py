from .errors import InvalidSeminaCommandError
from .models import CommissionSemina, CommissionSeminaResult
from .ports import SeminaCommissioningWriter


class SeminaCommissioningService:
    def __init__(self, writer: SeminaCommissioningWriter) -> None:
        self._writer = writer

    def commission(self, command: CommissionSemina) -> CommissionSeminaResult:
        if not isinstance(command, CommissionSemina):
            raise InvalidSeminaCommandError("command non valido.")
        return self._writer.commission(command)
