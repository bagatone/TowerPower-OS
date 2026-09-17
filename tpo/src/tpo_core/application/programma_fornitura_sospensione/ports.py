from typing import Protocol

from .models import (
    RiattivaProgrammaFornitura, RiattivaProgrammaFornituraResult,
    SospendiProgrammaFornitura, SospendiProgrammaFornituraResult,
)


class ProgrammaFornituraSospensioneWriter(Protocol):
    def sospendi(self, command: SospendiProgrammaFornitura) -> SospendiProgrammaFornituraResult: ...
    def riattiva(self, command: RiattivaProgrammaFornitura) -> RiattivaProgrammaFornituraResult: ...
