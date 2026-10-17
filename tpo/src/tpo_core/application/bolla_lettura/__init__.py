"""Boundary BOLLA DI CONSEGNA (sola lettura): CONSEGNA + provenienza di lotto."""

from .errors import (
    BollaLetturaError, ConsegnaNonConsegnataError, ConsegnaNonTrovataError,
    InvalidBollaLetturaQueryError, UnioneBolleError,
)
from .models import Bolla, OrigineLotto, PagamentoBolla, RichiediBolla, RigaBolla
from .ports import BollaLetturaReader
from .service import BollaLetturaService
from .unione import unisci_bolle

__all__ = [
    "Bolla",
    "BollaLetturaError",
    "BollaLetturaReader",
    "BollaLetturaService",
    "ConsegnaNonConsegnataError",
    "ConsegnaNonTrovataError",
    "InvalidBollaLetturaQueryError",
    "OrigineLotto",
    "PagamentoBolla",
    "RichiediBolla",
    "RigaBolla",
    "UnioneBolleError",
    "unisci_bolle",
]
