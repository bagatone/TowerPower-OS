from .errors import InvalidIncassoCommandError
from .models import (
    CorreggiIncasso, CorreggiIncassoResult, RegistraIncasso, RegistraIncassoResult,
)
from .ports import IncassoWriter


class IncassoService:
    def __init__(self, writer: IncassoWriter) -> None:
        self._writer = writer

    def record(self, command: RegistraIncasso) -> RegistraIncassoResult:
        if not isinstance(command, RegistraIncasso):
            raise InvalidIncassoCommandError("command non valido.")
        return self._writer.record(command)

    def correct(self, command: CorreggiIncasso) -> CorreggiIncassoResult:
        if not isinstance(command, CorreggiIncasso):
            raise InvalidIncassoCommandError("command non valido.")
        return self._writer.correct(command)
