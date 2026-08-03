"""Adapter Google Sheets conformi al Physical Schema Freeze v1.0."""

from .gateway import GoogleSheetsGateway
from .ordini_repository import GoogleSheetsOrdineRepository
from .programmi_repository import GoogleSheetsProgrammaFornituraRepository

__all__ = [
    "GoogleSheetsGateway",
    "GoogleSheetsOrdineRepository",
    "GoogleSheetsProgrammaFornituraRepository",
]
