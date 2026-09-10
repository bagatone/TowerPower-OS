"""Boundary applicativo CLIENTI V1 (query a sola lettura, Fase 1 OPERATIONAL_WEB_ADAPTER)."""

from .errors import (
    ClientiLetturaClienteNotFoundError,
    ClientiLetturaError,
    InvalidClientiLetturaQueryError,
)
from .models import Cliente, ElencoClienti, RichiediCliente, RichiediElencoClienti
from .ports import ClientiLetturaReader
from .service import ClientiLetturaService

__all__ = [
    "Cliente",
    "ClientiLetturaClienteNotFoundError",
    "ClientiLetturaError",
    "ClientiLetturaReader",
    "ClientiLetturaService",
    "ElencoClienti",
    "InvalidClientiLetturaQueryError",
    "RichiediCliente",
    "RichiediElencoClienti",
]
