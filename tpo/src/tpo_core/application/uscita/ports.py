from typing import Protocol

from .models import (
    CorreggiUscita, CorreggiUscitaResult, RegistraUscita, RegistraUscitaResult,
)


class UscitaWriter(Protocol):
    def record(self, command: RegistraUscita) -> RegistraUscitaResult: ...
    def correct(self, command: CorreggiUscita) -> CorreggiUscitaResult: ...
