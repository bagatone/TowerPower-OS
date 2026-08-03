"""Porta minima verso Google Sheets, priva di conoscenza del dominio."""

from __future__ import annotations

from typing import Protocol


class GoogleSheetsGateway(Protocol):
    def read_rows(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
    ) -> tuple[dict[str, str], ...]: ...

    def append_rows(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
        rows: tuple[dict[str, str], ...],
    ) -> None: ...
