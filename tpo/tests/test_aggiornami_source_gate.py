from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src import aggiornami
from src.github_loader import GitHubDocument
from src.sheets_loader import SheetData
from src.source_gate import (
    SourceNotAvailableError,
    SourceProvenance,
    build_google_sheets_provenance,
    current_timestamp,
)


AGGIORNAMI_SHEETS = [
    "CONSEGNE",
    "STOCK",
    "LOTTI",
    "SEMINE",
    "RACCOLTI",
    "PROBLEMI",
    "MASTER_VARIETA",
    "PIANO_SEMINE",
    "CALENDARIO_PRODUZIONE",
    "BRIEFING_GIORNALIERO",
]


def document(name: str, content: str = "# test") -> GitHubDocument:
    return GitHubDocument(
        name=name,
        path=f"docs/{name}",
        content=content,
        provenance=SourceProvenance(
            source_type="LOCAL",
            source_name=name,
            loaded_at=current_timestamp(),
            read_successfully=True,
            locator=f"docs/{name}",
            checksum="checksum",
        ),
    )


def documents() -> dict[str, GitHubDocument]:
    schema = Path("docs/TPO_SHEETS_SCHEMA.md").read_text(encoding="utf-8")
    return {
        "OPERATING_RULES.md": document("OPERATING_RULES.md"),
        "TPO_SHEETS_SCHEMA.md": document("TPO_SHEETS_SCHEMA.md", schema),
        "AGENTS.md": document("AGENTS.md"),
        "TPO_BOOTSTRAP.md": document("TPO_BOOTSTRAP.md"),
    }


def source_sheet(name: str, read_successfully: bool = True) -> SheetData:
    headers = ["ID"]
    return SheetData(
        name=name,
        headers=headers,
        rows=[],
        raw_values=[headers],
        provenance=build_google_sheets_provenance(
            sheet_name=name,
            spreadsheet_id="test",
            values=[headers],
            read_successfully=read_successfully,
        ),
    )


class FakeDocumentProvider:
    def load_documents(self) -> dict[str, GitHubDocument]:
        return documents()


class FakeSheetsLoader:
    def __init__(self, sheets: dict[str, SheetData]) -> None:
        self.sheets = sheets

    def load_required_sheets(self, names=None, expected_headers=None):
        return self.sheets


class AggiornamiSourceGateTest(unittest.TestCase):
    def test_aggiornami_missing_required_source_blocks_briefing(self) -> None:
        sheets = {
            name: source_sheet(name)
            for name in AGGIORNAMI_SHEETS
            if name != "STOCK"
        }

        with patch.object(aggiornami, "load_config", return_value={"dry_run": True}):
            with patch.object(aggiornami, "build_document_provider", return_value=FakeDocumentProvider()):
                with patch.object(aggiornami.SheetsLoader, "from_config", return_value=FakeSheetsLoader(sheets)):
                    with self.assertRaises(SourceNotAvailableError) as raised:
                        aggiornami.build_report("config/settings.yaml")

        self.assertEqual(raised.exception.status, "SOURCE_NOT_AVAILABLE")
        self.assertEqual(raised.exception.missing_sources, ["STOCK"])

    def test_aggiornami_main_does_not_print_operational_briefing_when_source_is_missing(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["aggiornami"]):
            with patch.object(
                aggiornami,
                "build_report",
                side_effect=SourceNotAvailableError(["CONSEGNE"]),
            ):
                with self.assertRaises(SystemExit):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        aggiornami.main()

        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("SOURCE_NOT_AVAILABLE", stderr.getvalue())
        self.assertNotIn("TOWER POWER OPERATIONS", stdout.getvalue())

    def test_aggiornami_with_all_required_sources_is_allowed_with_provenance(self) -> None:
        sheets = {name: source_sheet(name) for name in AGGIORNAMI_SHEETS}

        with patch.object(aggiornami, "load_config", return_value={"dry_run": True}):
            with patch.object(aggiornami, "build_document_provider", return_value=FakeDocumentProvider()):
                with patch.object(aggiornami.SheetsLoader, "from_config", return_value=FakeSheetsLoader(sheets)):
                    report = aggiornami.build_report("config/settings.yaml")

        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["source_gate"]["status"], "OK")
        self.assertIn("CONSEGNE", report["provenance"]["sheets"])
        self.assertEqual(
            report["provenance"]["sheets"]["CONSEGNE"]["source_type"],
            "GOOGLE_SHEETS",
        )


if __name__ == "__main__":
    unittest.main()
