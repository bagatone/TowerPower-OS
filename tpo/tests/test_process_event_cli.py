from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from src import process_event
from src.event_engine import EventDataContext, EventEngine, _load_schemas, build_demo_sheets
from tests.fixtures.legacy_google_sheets import legacy_schema_path


class ProcessEventCliTest(unittest.TestCase):
    def event_file(self) -> str:
        handle = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json")
        json.dump(
            {
                "event_id": "EVT-TEST-CLI",
                "event_type": "SEMINA",
                "timestamp": "2026-07-10T16:00:00",
                "timezone": "Atlantic/Canary",
                "operatore": "Matteo",
                "source": "cli",
                "status": "CONFERMATO",
                "payload": {
                    "varieta": "Cilantro",
                    "set": 6,
                    "unita": "set",
                    "data_semina": "2026-07-10",
                    "id_lotto": "CIL-CLI-TEST",
                },
            },
            handle,
        )
        handle.close()
        return handle.name

    def test_cli_dry_run_prints_ready_event(self) -> None:
        path = self.event_file()
        buffer = io.StringIO()
        schemas = _load_schemas(legacy_schema_path())
        engine = EventEngine.from_context(
            EventDataContext(sheets=build_demo_sheets(schemas), schemas=schemas)
        )
        with patch.object(sys, "argv", ["process_event", "--input", path, "--dry-run"]):
            with patch.object(EventEngine, "from_default_sources", return_value=engine):
                with patch.object(process_event, "validate_write_plan_offline", return_value=[]):
                    with redirect_stdout(buffer):
                        process_event.main()

        output = buffer.getvalue()
        self.assertIn("TOWERPOWER OS - EVENT ENGINE MVP", output)
        self.assertIn("Stato: PRONTO", output)
        self.assertIn("WritePlan:", output)
        self.assertIn("Nessuna scrittura eseguita.", output)

    def test_cli_blocks_apply(self) -> None:
        path = self.event_file()
        with patch.object(sys, "argv", ["process_event", "--input", path, "--apply"]):
            with self.assertRaises(SystemExit):
                process_event.main()


if __name__ == "__main__":
    unittest.main()
