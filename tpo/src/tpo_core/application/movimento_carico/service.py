"""Caso d'uso MOVIMENTO_CARICO_RACCOLTA."""

from .errors import InvalidMovimentoCaricoCommandError
from .models import RegistraCaricoMagazzino, RegistraCaricoMagazzinoResult
from .ports import MovimentoCaricoWriter


class MovimentoCaricoService:
    def __init__(self, writer: MovimentoCaricoWriter) -> None:
        self._writer = writer

    def registra(self, command: RegistraCaricoMagazzino) -> RegistraCaricoMagazzinoResult:
        if not isinstance(command, RegistraCaricoMagazzino):
            raise InvalidMovimentoCaricoCommandError("command non valido.")
        return self._writer.registra(command)
