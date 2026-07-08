from __future__ import annotations

import unittest
from decimal import Decimal

from src.sheets_loader import SheetData
from src.stock_alarm import StockAlarmEngine


class StockAlarmTest(unittest.TestCase):
    def test_decimal_with_dot_is_not_treated_as_integer(self) -> None:
        value = StockAlarmEngine()._decimal("0.5")

        self.assertEqual(value, Decimal("0.5"))

    def test_decimal_with_comma_is_supported(self) -> None:
        value = StockAlarmEngine()._decimal("0,5")

        self.assertEqual(value, Decimal("0.5"))

    def test_stock_alarm_only_on_rabano(self) -> None:
        sheet = SheetData(
            name="STOCK",
            headers=["VARIETÀ", "DISPONIBILE", "PRENOTATO"],
            raw_values=[],
            rows=[
                {"VARIETÀ": "rabano morado", "DISPONIBILE": "3", "PRENOTATO": "4"},
                {"VARIETÀ": "mizuna roja", "DISPONIBILE": "2", "PRENOTATO": "0.5"},
                {"VARIETÀ": "lenticchie", "DISPONIBILE": "1", "PRENOTATO": "0.5"},
                {"VARIETÀ": "hinojo", "DISPONIBILE": "1", "PRENOTATO": "0,5"},
                {"VARIETÀ": "col roja", "DISPONIBILE": "1", "PRENOTATO": "0.5"},
            ],
        )

        alarms = StockAlarmEngine().evaluate(sheet)

        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0].item, "rabano morado")
        self.assertEqual(alarms[0].prenotato, Decimal("4"))


if __name__ == "__main__":
    unittest.main()
