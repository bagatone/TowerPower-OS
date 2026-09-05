"""Caso d'uso ARTICOLO_COMMISSIONING."""

from .errors import InvalidArticoloCommandError
from .models import CommissionArticolo, CommissionArticoloResult
from .ports import ArticoloWriter


class ArticoloService:
    def __init__(self, writer: ArticoloWriter) -> None:
        self._writer = writer

    def commission(self, command: CommissionArticolo) -> CommissionArticoloResult:
        if not isinstance(command, CommissionArticolo):
            raise InvalidArticoloCommandError("command non valido.")
        return self._writer.commission(command)
