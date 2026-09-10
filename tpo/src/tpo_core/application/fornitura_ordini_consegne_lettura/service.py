"""Caso d'uso FORNITURA/ORDINI/CONSEGNE/ASSEGNAZIONE_FISICA (sola lettura)."""

from .errors import InvalidFornituraOrdiniConsegneLetturaQueryError
from .models import (
    ElencoAssegnazioniFisiche, ElencoConsegne, ElencoOrdini, ElencoProgrammiFornitura,
    RichiediElencoAssegnazioniFisiche, RichiediElencoConsegne, RichiediElencoOrdini,
    RichiediElencoProgrammiFornitura,
)
from .ports import FornituraOrdiniConsegneLetturaReader


class FornituraOrdiniConsegneLetturaService:
    def __init__(self, reader: FornituraOrdiniConsegneLetturaReader) -> None:
        self._reader = reader

    def programmi_fornitura(
        self, query: RichiediElencoProgrammiFornitura
    ) -> ElencoProgrammiFornitura:
        if not isinstance(query, RichiediElencoProgrammiFornitura):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("query non valida.")
        return self._reader.programmi_fornitura(query)

    def ordini(self, query: RichiediElencoOrdini) -> ElencoOrdini:
        if not isinstance(query, RichiediElencoOrdini):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("query non valida.")
        return self._reader.ordini(query)

    def consegne(self, query: RichiediElencoConsegne) -> ElencoConsegne:
        if not isinstance(query, RichiediElencoConsegne):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("query non valida.")
        return self._reader.consegne(query)

    def assegnazioni_fisiche(
        self, query: RichiediElencoAssegnazioniFisiche
    ) -> ElencoAssegnazioniFisiche:
        if not isinstance(query, RichiediElencoAssegnazioniFisiche):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("query non valida.")
        return self._reader.assegnazioni_fisiche(query)
