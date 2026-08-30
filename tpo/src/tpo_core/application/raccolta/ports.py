from typing import Protocol

from .models import RecordRaccolta, RecordRaccoltaResult


class RaccoltaWriter(Protocol):
    def record(self, command: RecordRaccolta) -> RecordRaccoltaResult: ...
