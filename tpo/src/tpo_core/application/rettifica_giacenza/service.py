"""Caso d'uso RETTIFICA_GIACENZA."""

from .errors import InvalidRettificaGiacenzaCommandError
from .models import RettificaGiacenza, RettificaGiacenzaResult
from .ports import RettificaGiacenzaWriter


class RettificaGiacenzaService:
    def __init__(self, writer: RettificaGiacenzaWriter) -> None:
        self._writer = writer

    def registra(self, command: RettificaGiacenza) -> RettificaGiacenzaResult:
        if not isinstance(command, RettificaGiacenza):
            raise InvalidRettificaGiacenzaCommandError("command non valido.")
        return self._writer.registra(command)
