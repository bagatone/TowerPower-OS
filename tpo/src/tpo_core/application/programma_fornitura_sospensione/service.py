from .errors import InvalidProgrammaFornituraSospensioneCommandError
from .models import (
    RiattivaProgrammaFornitura, RiattivaProgrammaFornituraResult,
    SospendiProgrammaFornitura, SospendiProgrammaFornituraResult,
)
from .ports import ProgrammaFornituraSospensioneWriter


class ProgrammaFornituraSospensioneService:
    def __init__(self, writer: ProgrammaFornituraSospensioneWriter) -> None:
        self._writer = writer

    def sospendi(self, command: SospendiProgrammaFornitura) -> SospendiProgrammaFornituraResult:
        if not isinstance(command, SospendiProgrammaFornitura):
            raise InvalidProgrammaFornituraSospensioneCommandError("command non valido.")
        return self._writer.sospendi(command)

    def riattiva(self, command: RiattivaProgrammaFornitura) -> RiattivaProgrammaFornituraResult:
        if not isinstance(command, RiattivaProgrammaFornitura):
            raise InvalidProgrammaFornituraSospensioneCommandError("command non valido.")
        return self._writer.riattiva(command)
