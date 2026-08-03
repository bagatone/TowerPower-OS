"""Adapter Google Sheets del ProgrammaFornituraRepository."""

from __future__ import annotations

from ...domain.entities.programma_fornitura import ProgrammaFornitura
from .gateway import GoogleSheetsGateway
from .mappers import PROGRAMMI_SHEET_NAME, programmi_from_rows


class GoogleSheetsProgrammaFornituraRepository:
    def __init__(self, spreadsheet_id: str, gateway: GoogleSheetsGateway, sheet_name: str = PROGRAMMI_SHEET_NAME) -> None:
        self._spreadsheet_id = spreadsheet_id
        self._gateway = gateway
        self._sheet_name = sheet_name

    def list_for_scheduling(self) -> tuple[ProgrammaFornitura, ...]:
        rows = self._gateway.read_rows(
            spreadsheet_id=self._spreadsheet_id,
            sheet_name=self._sheet_name,
        )
        return programmi_from_rows(rows)
