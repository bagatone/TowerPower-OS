from .errors import InvalidUscitaCommandError
from .models import (
    CorreggiUscita, CorreggiUscitaResult, RegistraUscita, RegistraUscitaResult,
)
from .ports import UscitaWriter


class UscitaService:
    def __init__(self, writer: UscitaWriter) -> None:
        self._writer = writer

    def record(self, command: RegistraUscita) -> RegistraUscitaResult:
        if not isinstance(command, RegistraUscita):
            raise InvalidUscitaCommandError("command non valido.")
        return self._writer.record(command)

    def correct(self, command: CorreggiUscita) -> CorreggiUscitaResult:
        if not isinstance(command, CorreggiUscita):
            raise InvalidUscitaCommandError("command non valido.")
        return self._writer.correct(command)
