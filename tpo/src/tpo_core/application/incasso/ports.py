from typing import Protocol

from .models import (
    CorreggiIncasso, CorreggiIncassoResult, RegistraIncasso, RegistraIncassoResult,
)


class IncassoWriter(Protocol):
    def record(self, command: RegistraIncasso) -> RegistraIncassoResult: ...
    def correct(self, command: CorreggiIncasso) -> CorreggiIncassoResult: ...
