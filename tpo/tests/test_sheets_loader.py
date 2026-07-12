from __future__ import annotations

import unittest

from src.sheets_loader import SheetsLoader
from src.source_gate import build_google_sheets_provenance


class SheetsLoaderTest(unittest.TestCase):
    def test_lotti_headers_are_recovered_from_schema_when_first_row_is_data(self) -> None:
        loader = SheetsLoader(
            spreadsheet_id="test",
            credentials_file="config/google-service-account.json",
        )
        expected_headers = [
            "CALENDARIO_PROD",
            "SET",
            "VARIETA",
            "DATA_SEMINA",
            "DATA_PASSAGGIO",
            "FASE",
            "STATO",
            "DATA_RACCOLTA",
            "NOTE",
        ]
        sheet = loader._to_sheet_data(
            "LOTTI",
            values=[
                [],
                [
                    "AFI-2806-A",
                    "6",
                    "guisante afila",
                    "28/06/2026",
                    "03/07/2026",
                    "luce",
                    "ok",
                    "10/07/2026",
                    "passaggio a luce 03/07",
                ],
            ],
            expected_headers=expected_headers,
            provenance=build_google_sheets_provenance("LOTTI", "test", [["LOTTI"]]),
        )

        self.assertEqual(sheet.headers, expected_headers)
        self.assertEqual(sheet.rows[0]["CALENDARIO_PROD"], "AFI-2806-A")
        self.assertEqual(sheet.rows[0]["VARIETA"], "guisante afila")
        self.assertEqual(sheet.provenance.source, "google_sheets")


if __name__ == "__main__":
    unittest.main()
