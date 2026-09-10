"""Boundary applicativo SEMENTE/LOTTO_SEME V1 (sola lettura, Fase 1 OPERATIONAL_WEB_ADAPTER)."""

from .errors import (
    InvalidSementeLetturaQueryError, SementeLetturaError, SementeLetturaLottoNotFoundError,
)
from .models import (
    ElencoLotti, ElencoSementi, LottoSeme, RichiediElencoLotti,
    RichiediElencoSementi, RichiediLotto, Semente,
)
from .ports import SementeLetturaReader
from .service import SementeLetturaService

__all__ = [
    "ElencoLotti",
    "ElencoSementi",
    "InvalidSementeLetturaQueryError",
    "LottoSeme",
    "RichiediElencoLotti",
    "RichiediElencoSementi",
    "RichiediLotto",
    "Semente",
    "SementeLetturaError",
    "SementeLetturaLottoNotFoundError",
    "SementeLetturaReader",
    "SementeLetturaService",
]
