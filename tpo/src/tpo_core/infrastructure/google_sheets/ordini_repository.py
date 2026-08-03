"""Adapter Google Sheets dell'OrdineRepository."""

from __future__ import annotations

from ...application.scheduling.models import ScheduledOrderRecord
from .gateway import GoogleSheetsGateway
from .mappers import (
    ORDINI_SHEET_NAME,
    scheduled_orders_from_rows,
    scheduled_orders_to_rows,
)


class GoogleSheetsOrdineRepository:
    def __init__(self, spreadsheet_id: str, gateway: GoogleSheetsGateway, sheet_name: str = ORDINI_SHEET_NAME) -> None:
        self._spreadsheet_id = spreadsheet_id
        self._gateway = gateway
        self._sheet_name = sheet_name

    def list_scheduled_orders(self) -> tuple[ScheduledOrderRecord, ...]:
        rows = self._gateway.read_rows(
            spreadsheet_id=self._spreadsheet_id,
            sheet_name=self._sheet_name,
        )
        return scheduled_orders_from_rows(rows)

    def add_scheduled_orders(self, records: tuple[ScheduledOrderRecord, ...]) -> None:
        if not records:
            return
        self._gateway.append_rows(
            spreadsheet_id=self._spreadsheet_id,
            sheet_name=self._sheet_name,
            rows=scheduled_orders_to_rows(records),
        )
