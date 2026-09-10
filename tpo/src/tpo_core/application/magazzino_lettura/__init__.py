"""Boundary MAGAZZINO (sola lettura): STOCK + MOVIMENTO_MAGAZZINO + ARTICOLO."""

from .errors import InvalidMagazzinoLetturaQueryError, MagazzinoLetturaError
from .models import (
    Articolo, ElencoArticoli, ElencoMovimenti, ElencoStock, MovimentoMagazzino,
    RichiediElencoArticoli, RichiediElencoMovimenti, RichiediElencoStock,
    StockArticolo, StockVarieta,
)
from .ports import MagazzinoLetturaReader
from .service import MagazzinoLetturaService

__all__ = [
    "Articolo",
    "ElencoArticoli",
    "ElencoMovimenti",
    "ElencoStock",
    "InvalidMagazzinoLetturaQueryError",
    "MagazzinoLetturaError",
    "MagazzinoLetturaReader",
    "MagazzinoLetturaService",
    "MovimentoMagazzino",
    "RichiediElencoArticoli",
    "RichiediElencoMovimenti",
    "RichiediElencoStock",
    "StockArticolo",
    "StockVarieta",
]
