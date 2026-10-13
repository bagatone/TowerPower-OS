from .errors import InvalidPagamentoConsegnaCommandError
from .models import (
    AnnullaPagamentoConsegna, AnnullaPagamentoConsegnaResult, RegistraPagamentoConsegna,
    RegistraPagamentoConsegnaResult,
)
from .ports import PagamentoConsegnaWriter


class PagamentoConsegnaService:
    def __init__(self, writer: PagamentoConsegnaWriter) -> None:
        self._writer = writer

    def record(self, command: RegistraPagamentoConsegna) -> RegistraPagamentoConsegnaResult:
        if not isinstance(command, RegistraPagamentoConsegna):
            raise InvalidPagamentoConsegnaCommandError("command non valido.")
        return self._writer.record(command)

    def cancel(self, command: AnnullaPagamentoConsegna) -> AnnullaPagamentoConsegnaResult:
        if not isinstance(command, AnnullaPagamentoConsegna):
            raise InvalidPagamentoConsegnaCommandError("command non valido.")
        return self._writer.cancel(command)
