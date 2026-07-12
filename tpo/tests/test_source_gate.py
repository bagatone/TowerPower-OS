from __future__ import annotations

import unittest

from src.github_loader import GitHubDocument
from src.sheets_loader import SheetData
from src.source_gate import (
    SOURCE_NOT_AVAILABLE,
    SourceGate,
    SourceGateError,
    SourceProvenance,
    build_content_checksum,
    build_google_sheets_provenance,
    current_timestamp,
)


def sheet(
    name: str,
    source_type: str = "GOOGLE_SHEETS",
    read_successfully: bool = True,
) -> SheetData:
    return SheetData(
        name=name,
        headers=["ID"],
        rows=[],
        raw_values=[["ID"]],
        provenance=SourceProvenance(
            source_type=source_type,
            source_name=name,
            loaded_at=current_timestamp(),
            read_successfully=read_successfully,
            sheet_name=name,
            locator=f"test:{name}!A:ZZ",
            checksum=build_content_checksum([[name]]),
        ),
    )


class SourceGateTest(unittest.TestCase):
    def test_allows_configured_document_source_with_checksum(self) -> None:
        document = GitHubDocument(
            name="OPERATING_RULES.md",
            path="OPERATING_RULES.md",
            content="# rules",
            provenance=SourceProvenance(
                source_type="LOCAL",
                source_name="OPERATING_RULES.md",
                loaded_at=current_timestamp(),
                read_successfully=True,
                locator="docs/OPERATING_RULES.md",
                checksum=build_content_checksum("# rules"),
            ),
        )

        SourceGate(require_checksum=True).assert_documents({"OPERATING_RULES.md": document})

    def test_blocks_untrusted_document_source(self) -> None:
        document = GitHubDocument(
            name="OPERATING_RULES.md",
            path="OPERATING_RULES.md",
            content="# rules",
            provenance=SourceProvenance(
                source_type="CHAT_MEMORY",
                source_name="OPERATING_RULES.md",
                loaded_at=current_timestamp(),
                read_successfully=True,
                locator="chat",
                checksum=build_content_checksum("# rules"),
            ),
        )

        with self.assertRaises(SourceGateError) as raised:
            SourceGate().assert_documents({"OPERATING_RULES.md": document})

        self.assertIn("sorgente non autorizzata", str(raised.exception))

    def test_consegne_without_consegne_loaded_is_source_not_available(self) -> None:
        result = SourceGate().check_request("consegne", {})

        self.assertEqual(result.status, SOURCE_NOT_AVAILABLE)
        self.assertEqual(result.missing_sources, ["CONSEGNE"])

    def test_consegne_with_only_tpo_narrative_is_source_not_available(self) -> None:
        result = SourceGate().check_request(
            "consegne",
            {"CONSEGNE": sheet("CONSEGNE", source_type="TPO_NARRATIVE")},
        )

        self.assertEqual(result.status, SOURCE_NOT_AVAILABLE)
        self.assertEqual(result.missing_sources, ["CONSEGNE"])

    def test_stock_without_stock_is_source_not_available(self) -> None:
        result = SourceGate().check_request("stock", {"CONSEGNE": sheet("CONSEGNE")})

        self.assertEqual(result.status, SOURCE_NOT_AVAILABLE)
        self.assertEqual(result.missing_sources, ["STOCK"])

    def test_clienti_without_clienti_is_source_not_available(self) -> None:
        result = SourceGate().check_request("clienti", {"STOCK": sheet("STOCK")})

        self.assertEqual(result.status, SOURCE_NOT_AVAILABLE)
        self.assertEqual(result.missing_sources, ["CLIENTI"])

    def test_read_successfully_false_blocks_request(self) -> None:
        result = SourceGate().check_request(
            "stock",
            {"STOCK": sheet("STOCK", read_successfully=False)},
        )

        self.assertEqual(result.status, SOURCE_NOT_AVAILABLE)
        self.assertEqual(result.missing_sources, ["STOCK"])

    def test_chat_memory_is_not_accepted_as_official_source(self) -> None:
        result = SourceGate().check_request(
            "stock",
            {"STOCK": sheet("STOCK", source_type="CHAT_MEMORY")},
        )

        self.assertEqual(result.status, SOURCE_NOT_AVAILABLE)

    def test_user_confirmed_current_turn_does_not_replace_stock(self) -> None:
        result = SourceGate().check_request(
            "stock",
            {"STOCK": sheet("STOCK", source_type="USER_CONFIRMED_CURRENT_TURN")},
        )

        self.assertEqual(result.status, SOURCE_NOT_AVAILABLE)

    def test_google_sheets_source_returns_validated_provenance(self) -> None:
        stock = SheetData(
            name="STOCK",
            headers=["ID"],
            rows=[],
            raw_values=[["ID"]],
            provenance=build_google_sheets_provenance("STOCK", "test", [["ID"]]),
        )

        result = SourceGate().check_request("stock", {"STOCK": stock})

        self.assertEqual(result.status, "OK")
        self.assertEqual(result.provenance[0].source_type, "GOOGLE_SHEETS")
        self.assertTrue(result.provenance[0].read_successfully)


if __name__ == "__main__":
    unittest.main()
