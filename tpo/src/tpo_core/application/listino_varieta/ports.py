from typing import Protocol

from .models import ImpostaPrezzoListinoVarieta, ImpostaPrezzoListinoVarietaResult


class ListinoVarietaWriter(Protocol):
    def imposta_prezzo(
        self, command: ImpostaPrezzoListinoVarieta
    ) -> ImpostaPrezzoListinoVarietaResult: ...
