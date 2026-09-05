"""Boundary applicativo DISPONIBILITA_COMMERCIALE V1 (query a sola lettura)."""

from .errors import (
    DisponibilitaCommercialeError,
    DisponibilitaCommercialeVarietaNotFoundError,
    InvalidDisponibilitaCommercialeQueryError,
)
from .models import DisponibilitaCommerciale, RichiediDisponibilitaCommerciale
from .ports import DisponibilitaCommercialeReader
from .service import DisponibilitaCommercialeService

__all__ = [
    "DisponibilitaCommerciale",
    "DisponibilitaCommercialeError",
    "DisponibilitaCommercialeReader",
    "DisponibilitaCommercialeService",
    "DisponibilitaCommercialeVarietaNotFoundError",
    "InvalidDisponibilitaCommercialeQueryError",
    "RichiediDisponibilitaCommerciale",
]
