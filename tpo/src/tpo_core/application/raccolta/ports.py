from typing import Protocol

from .models import CorreggiRaccolta, CorreggiRaccoltaResult, RecordRaccolta, RecordRaccoltaResult


class RaccoltaWriter(Protocol):
    def record(self, command: RecordRaccolta) -> RecordRaccoltaResult: ...
    def correct(self, command: CorreggiRaccolta) -> CorreggiRaccoltaResult: ...
