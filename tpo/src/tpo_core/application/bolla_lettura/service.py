"""Caso d'uso BOLLA DI CONSEGNA (query a sola lettura)."""

from .errors import ConsegnaNonConsegnataError, InvalidBollaLetturaQueryError
from .models import Bolla, RichiediBolla
from .ports import BollaLetturaReader


class BollaLetturaService:
    def __init__(self, reader: BollaLetturaReader) -> None:
        self._reader = reader

    def bolla(self, query: RichiediBolla) -> Bolla:
        if not isinstance(query, RichiediBolla):
            raise InvalidBollaLetturaQueryError("query non valida.")
        result = self._reader.bolla(query)
        if result.stato != "CONSEGNATA":
            raise ConsegnaNonConsegnataError(
                f"La CONSEGNA {result.consegna_id.value} e' in stato {result.stato}: "
                "la BOLLA si emette solo per una CONSEGNA CONSEGNATA."
            )
        return result
