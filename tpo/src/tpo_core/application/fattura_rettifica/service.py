"""Caso d'uso FATTURA_RETTIFICA."""

from .errors import InvalidRectifyFatturaCommandError
from .models import RectifyFattura, RectifyFatturaResult
from .ports import FatturaRettificaWriter


class FatturaRettificaService:
    def __init__(self, writer: FatturaRettificaWriter) -> None:
        self._writer = writer

    def rectify(self, command: RectifyFattura) -> RectifyFatturaResult:
        if not isinstance(command, RectifyFattura):
            raise InvalidRectifyFatturaCommandError("command non valido.")
        return self._writer.rectify(command)
