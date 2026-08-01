"""Entità del Core Domain."""

from .movimento_magazzino import MovimentoMagazzino
from .raccolta import Raccolta
from .semina import Semina
from .stock import Stock
from .varieta import Varieta

__all__ = ["MovimentoMagazzino", "Raccolta", "Semina", "Stock", "Varieta"]
