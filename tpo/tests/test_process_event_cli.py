from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from src import process_event


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
        with patch.object(sys, "argv", ["process_event", "--input", path, "--dry-run"]):
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
