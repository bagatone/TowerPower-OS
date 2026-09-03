"""Caso d'uso FATTURA_EMISSIONE."""

from .errors import InvalidEmitFatturaCommandError
from .models import EmitFattura, EmitFatturaResult
from .ports import FatturaEmissioneWriter


class FatturaEmissioneService:
    def __init__(self, writer: FatturaEmissioneWriter) -> None:
        self._writer = writer

    def emit(self, command: EmitFattura) -> EmitFatturaResult:
        if not isinstance(command, EmitFattura):
            raise InvalidEmitFatturaCommandError("command non valido.")
        return self._writer.emit(command)
