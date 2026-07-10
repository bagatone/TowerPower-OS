from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src import write_sheets
from src.sheets_writer import WriteResult


class FakeWriter:
    def dry_run(self, plan):
        return WriteResult(
            mode="dry-run",
            success=True,
            rows_requested={"FORNITORI": 1},
            rows_valid={"FORNITORI": 1},
            log_path="outputs/write_logs/test.json",
        )

    def apply(self, plan):
        return WriteResult(
            mode="apply",
            success=True,
            rows_requested={"FORNITORI": 1},
            rows_valid={"FORNITORI": 1},
            rows_written={"FORNITORI": 1},
            log_path="outputs/write_logs/test.json",
        )


class WriteSheetsCliTest(unittest.TestCase):
    def write_plan_file(self) -> str:
        handle = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json")
        json.dump(
            {
                "operations": [
                    {
                        "sheet_name": "FORNITORI",
                        "mode": "append",
                        "rows": [{"ID_FORNITORE": "F-001"}],
                    }
                ]
            },
            handle,
        )
        handle.close()
        return handle.name

    def test_cli_dry_run_prints_result(self) -> None:
        path = self.write_plan_file()
        buffer = io.StringIO()
        with patch.object(sys, "argv", ["write_sheets", "--input", path, "--dry-run"]):
            with patch.object(write_sheets.SheetsWriter, "from_config_path", return_value=FakeWriter()):
                with redirect_stdout(buffer):
                    write_sheets.main()

        self.assertIn("Modalità: DRY-RUN", buffer.getvalue())
        self.assertIn("Nessuna scrittura eseguita.", buffer.getvalue())

    def test_cli_apply_prints_written_rows(self) -> None:
        path = self.write_plan_file()
        buffer = io.StringIO()
        with patch.object(sys, "argv", ["write_sheets", "--input", path, "--apply"]):
            with patch.object(write_sheets.SheetsWriter, "from_config_path", return_value=FakeWriter()):
                with redirect_stdout(buffer):
                    write_sheets.main()

        self.assertIn("Righe scritte:", buffer.getvalue())
        self.assertIn("FORNITORI: 1", buffer.getvalue())

    def test_cli_requires_mode(self) -> None:
        path = self.write_plan_file()
        with patch.object(sys, "argv", ["write_sheets", "--input", path]):
            with self.assertRaises(SystemExit):
                write_sheets.main()


if __name__ == "__main__":
    unittest.main()
