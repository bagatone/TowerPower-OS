from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .sheets_loader import SheetData


@dataclass(frozen=True)
class StockAlarm:
    row_number: int
    item: str
    disponibile: Decimal
    prenotato: Decimal
    alarm: str = "ALLARME ROSSO"
    priority: str = "PRIORITÀ ASSOLUTA"


class StockAlarmEngine:
    def evaluate(self, stock_sheet: SheetData) -> list[StockAlarm]:
        alarms: list[StockAlarm] = []

        for index, row in enumerate(stock_sheet.rows, start=2):
            disponibile = self._decimal(row.get("DISPONIBILE", "0"))
            prenotato = self._decimal(row.get("PRENOTATO", "0"))
            if disponibile < prenotato:
                alarms.append(
                    StockAlarm(
                        row_number=index,
                        item=self._label(row),
                        disponibile=disponibile,
                        prenotato=prenotato,
                    )
                )

        return alarms

    def _decimal(self, value: str) -> Decimal:
        normalized = str(value).strip().replace(",", ".")
        if not normalized:
            return Decimal("0")
        try:
            return Decimal(normalized)
        except InvalidOperation:
            return Decimal("0")

    def _label(self, row: dict[str, str]) -> str:
        for key in ("LOTTO", "VARIETA", "VARIETÀ", "PRODOTTO", "CODICE", "ID"):
            if row.get(key):
                return row[key]
        return "Riga stock senza etichetta"
