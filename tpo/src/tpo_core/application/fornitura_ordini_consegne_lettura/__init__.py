"""Boundary FORNITURA/ORDINI/CONSEGNE/ASSEGNAZIONE_FISICA (sola lettura)."""

from .errors import (
    FornituraOrdiniConsegneLetturaError, InvalidFornituraOrdiniConsegneLetturaQueryError,
)
from .models import (
    AssegnazioneFisica, Consegna, ElencoAssegnazioniFisiche, ElencoConsegne, ElencoOrdini,
    ElencoProgrammiFornitura, Ordine, ProgrammaFornitura, RichiediElencoAssegnazioniFisiche,
    RichiediElencoConsegne, RichiediElencoOrdini, RichiediElencoProgrammiFornitura,
    RigaConsegna, RigaOrdine, RigaProgrammaFornitura,
)
from .ports import FornituraOrdiniConsegneLetturaReader
from .service import FornituraOrdiniConsegneLetturaService

__all__ = [
    "AssegnazioneFisica",
    "Consegna",
    "ElencoAssegnazioniFisiche",
    "ElencoConsegne",
    "ElencoOrdini",
    "ElencoProgrammiFornitura",
    "FornituraOrdiniConsegneLetturaError",
    "FornituraOrdiniConsegneLetturaReader",
    "FornituraOrdiniConsegneLetturaService",
    "InvalidFornituraOrdiniConsegneLetturaQueryError",
    "Ordine",
    "ProgrammaFornitura",
    "RichiediElencoAssegnazioniFisiche",
    "RichiediElencoConsegne",
    "RichiediElencoOrdini",
    "RichiediElencoProgrammiFornitura",
    "RigaConsegna",
    "RigaOrdine",
    "RigaProgrammaFornitura",
]
