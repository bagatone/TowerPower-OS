"""Boundary FINANZE (sola lettura): FATTURA + INCASSO + USCITA."""

from .errors import FinanzeLetturaError, InvalidFinanzeLetturaQueryError
from .models import (
    ElencoFatture, ElencoIncassi, ElencoUscite, Fattura, Incasso,
    RichiediElencoFatture, RichiediElencoIncassi, RichiediElencoUscite, RigaFattura, Uscita,
)
from .ports import FinanzeLetturaReader
from .service import FinanzeLetturaService

__all__ = [
    "ElencoFatture",
    "ElencoIncassi",
    "ElencoUscite",
    "Fattura",
    "FinanzeLetturaError",
    "FinanzeLetturaReader",
    "FinanzeLetturaService",
    "Incasso",
    "InvalidFinanzeLetturaQueryError",
    "RichiediElencoFatture",
    "RichiediElencoIncassi",
    "RichiediElencoUscite",
    "RigaFattura",
    "Uscita",
]
