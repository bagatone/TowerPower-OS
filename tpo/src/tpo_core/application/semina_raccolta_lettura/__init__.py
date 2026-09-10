"""Boundary applicativo SEMINA/RACCOLTA V1 (sola lettura, Fase 1 OPERATIONAL_WEB_ADAPTER)."""

from .errors import (
    InvalidSeminaRaccoltaLetturaQueryError,
    SeminaRaccoltaLetturaError,
    SeminaRaccoltaLetturaSeminaNotFoundError,
)
from .models import (
    ElencoSemine, ESITI_SEMINA_AMMESSI, Raccolta, RichiediElencoSemine, RichiediSemina,
    Semina, STATI_SEMINA_AMMESSI,
)
from .ports import SeminaRaccoltaLetturaReader
from .service import SeminaRaccoltaLetturaService

__all__ = [
    "ElencoSemine",
    "ESITI_SEMINA_AMMESSI",
    "InvalidSeminaRaccoltaLetturaQueryError",
    "Raccolta",
    "RichiediElencoSemine",
    "RichiediSemina",
    "Semina",
    "SeminaRaccoltaLetturaError",
    "SeminaRaccoltaLetturaReader",
    "SeminaRaccoltaLetturaService",
    "SeminaRaccoltaLetturaSeminaNotFoundError",
    "STATI_SEMINA_AMMESSI",
]
