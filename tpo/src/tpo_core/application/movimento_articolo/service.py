"""Caso d'uso MOVIMENTO_ARTICOLO."""

from .errors import InvalidMovimentoArticoloCommandError
from .models import RegistraMovimentoArticolo, RegistraMovimentoArticoloResult
from .ports import MovimentoArticoloWriter


class MovimentoArticoloService:
    def __init__(self, writer: MovimentoArticoloWriter) -> None:
        self._writer = writer

    def registra(
        self, command: RegistraMovimentoArticolo
    ) -> RegistraMovimentoArticoloResult:
        if not isinstance(command, RegistraMovimentoArticolo):
            raise InvalidMovimentoArticoloCommandError("command non valido.")
        return self._writer.registra(command)
