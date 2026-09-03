from .errors import InvalidRaccoltaCommandError
from .models import (
    CorreggiRaccolta, CorreggiRaccoltaResult, RecordRaccolta, RecordRaccoltaResult,
)
from .ports import RaccoltaWriter


class RaccoltaService:
    def __init__(self, writer: RaccoltaWriter) -> None:
        self._writer = writer

    def record(self, command: RecordRaccolta) -> RecordRaccoltaResult:
        if not isinstance(command, RecordRaccolta):
            raise InvalidRaccoltaCommandError("command non valido.")
        return self._writer.record(command)

    def correct(self, command: CorreggiRaccolta) -> CorreggiRaccoltaResult:
        if not isinstance(command, CorreggiRaccolta):
            raise InvalidRaccoltaCommandError("command non valido.")
        return self._writer.correct(command)
