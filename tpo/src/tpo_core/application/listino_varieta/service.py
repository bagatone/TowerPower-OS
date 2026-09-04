from .errors import InvalidListinoVarietaCommandError
from .models import ImpostaPrezzoListinoVarieta, ImpostaPrezzoListinoVarietaResult
from .ports import ListinoVarietaWriter


class ListinoVarietaService:
    def __init__(self, writer: ListinoVarietaWriter) -> None:
        self._writer = writer

    def imposta_prezzo(
        self, command: ImpostaPrezzoListinoVarieta
    ) -> ImpostaPrezzoListinoVarietaResult:
        if not isinstance(command, ImpostaPrezzoListinoVarieta):
            raise InvalidListinoVarietaCommandError("command ImpostaPrezzoListinoVarieta non valido.")
        return self._writer.imposta_prezzo(command)
