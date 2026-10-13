from typing import Protocol

from .models import (
    AnnullaPagamentoConsegna, AnnullaPagamentoConsegnaResult, RegistraPagamentoConsegna,
    RegistraPagamentoConsegnaResult,
)


class PagamentoConsegnaWriter(Protocol):
    def record(self, command: RegistraPagamentoConsegna) -> RegistraPagamentoConsegnaResult: ...
    def cancel(self, command: AnnullaPagamentoConsegna) -> AnnullaPagamentoConsegnaResult: ...
