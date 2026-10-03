"""Caso d'uso ORDINE_MANUALE."""

from .errors import InvalidOrdineManualeCommandError
from .models import RegistraOrdineManuale, RegistraOrdineManualeResult
from .ports import OrdineManualeWriter


class OrdineManualeService:
    def __init__(self, writer: OrdineManualeWriter) -> None:
        self._writer = writer

    def registra(self, command: RegistraOrdineManuale) -> RegistraOrdineManualeResult:
        if not isinstance(command, RegistraOrdineManuale):
            raise InvalidOrdineManualeCommandError("command non valido.")
        return self._writer.registra(command)
