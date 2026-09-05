"""Caso d'uso ASSEGNAZIONE_FISICA."""

from .errors import InvalidAssegnazioneFisicaCommandError
from .models import RegistraAssegnazioneFisica, RegistraAssegnazioneFisicaResult
from .ports import AssegnazioneFisicaWriter


class AssegnazioneFisicaService:
    def __init__(self, writer: AssegnazioneFisicaWriter) -> None:
        self._writer = writer

    def registra(
        self, command: RegistraAssegnazioneFisica
    ) -> RegistraAssegnazioneFisicaResult:
        if not isinstance(command, RegistraAssegnazioneFisica):
            raise InvalidAssegnazioneFisicaCommandError("command non valido.")
        return self._writer.registra(command)
