"""Porta del reader a sola lettura FORNITURA/ORDINI/CONSEGNE/ASSEGNAZIONE_FISICA."""

from typing import Protocol

from .models import (
    ElencoAssegnazioniFisiche, ElencoConsegne, ElencoOrdini, ElencoProgrammiFornitura,
    RichiediElencoAssegnazioniFisiche, RichiediElencoConsegne, RichiediElencoOrdini,
    RichiediElencoProgrammiFornitura,
)


class FornituraOrdiniConsegneLetturaReader(Protocol):
    def programmi_fornitura(
        self, query: RichiediElencoProgrammiFornitura
    ) -> ElencoProgrammiFornitura:
        """Legge i PROGRAMMI_FORNITURA con versione corrente attiva. Sola lettura."""
        ...

    def ordini(self, query: RichiediElencoOrdini) -> ElencoOrdini:
        """Legge l'elenco completo degli ORDINI con le loro righe. Sola lettura."""
        ...

    def consegne(self, query: RichiediElencoConsegne) -> ElencoConsegne:
        """Legge l'elenco completo delle CONSEGNE con righe e ordini collegati. Sola lettura."""
        ...

    def assegnazioni_fisiche(
        self, query: RichiediElencoAssegnazioniFisiche
    ) -> ElencoAssegnazioniFisiche:
        """Legge l'elenco completo delle ASSEGNAZIONI_FISICHE. Sola lettura."""
        ...
