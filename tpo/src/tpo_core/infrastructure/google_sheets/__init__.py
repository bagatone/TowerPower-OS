"""Adapter Google Sheets conformi al Physical Schema Freeze v1.0."""

from .commit_repository import GoogleSheetsCommitRepository
from .gateway import GoogleSheetsGateway
from .google_api_gateway import GoogleApiSheetsGateway, build_google_sheets_service
from .ordini_repository import GoogleSheetsOrdineRepository
from .programmi_repository import GoogleSheetsProgrammaFornituraRepository

__all__ = [
    "GoogleSheetsGateway",
    "GoogleApiSheetsGateway",
    "GoogleSheetsCommitRepository",
    "GoogleSheetsOrdineRepository",
    "GoogleSheetsProgrammaFornituraRepository",
    "build_google_sheets_service",
]
