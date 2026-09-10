"""Boundary applicativo VARIETA/LISTINO_VARIETA V1 (sola lettura, Fase 1 OPERATIONAL_WEB_ADAPTER)."""

from .errors import (
    InvalidVarietaLetturaQueryError,
    VarietaLetturaError,
    VarietaLetturaVarietaNotFoundError,
)
from .models import (
    ElencoVarieta, RichiediElencoVarieta, RichiediVarieta, STATI_VARIETA_AMMESSI, Varieta,
)
from .ports import VarietaLetturaReader
from .service import VarietaLetturaService

__all__ = [
    "ElencoVarieta",
    "InvalidVarietaLetturaQueryError",
    "RichiediElencoVarieta",
    "RichiediVarieta",
    "STATI_VARIETA_AMMESSI",
    "Varieta",
    "VarietaLetturaError",
    "VarietaLetturaReader",
    "VarietaLetturaService",
    "VarietaLetturaVarietaNotFoundError",
]
