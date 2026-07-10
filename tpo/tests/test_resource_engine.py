from __future__ import annotations

import unittest
from pathlib import Path

from src.init_resource_engine import (
    INITIAL_ROWS,
    RESOURCE_HEADERS,
    build_resource_plan,
    summarize_plan,
    validate_initial_data,
    _missing_rows,
)
from src.schema_validator import SchemaValidator
from src.sheets_loader import REQUIRED_SHEETS


RESOURCE_SHEETS = [
    "ANAGRAFICA_ARTICOLI",
    "INVENTARIO",
    "MOVIMENTI_MAGAZZINO",
    "RICETTE_PRODUZIONE",
    "FORNITORI",
]


class ResourceEngineTest(unittest.TestCase):
    def test_required_sheets_include_resource_engine_sheets(self) -> None:
        for sheet_name in RESOURCE_SHEETS:
            self.assertIn(sheet_name, REQUIRED_SHEETS)

    def test_schema_contains_resource_engine_headers(self) -> None:
        markdown = Path("docs/TPO_SHEETS_SCHEMA.md").read_text(encoding="utf-8")
        schemas = SchemaValidator().parse_schema(markdown)

        for sheet_name in RESOURCE_SHEETS:
            self.assertEqual(schemas[sheet_name].headers, RESOURCE_HEADERS[sheet_name])

    def test_initial_data_row_lengths_match_headers(self) -> None:
        plan = build_resource_plan()

        self.assertEqual(validate_initial_data(plan), [])

    def test_missing_rows_avoids_duplicates(self) -> None:
        headers = RESOURCE_HEADERS["INVENTARIO"]
        desired_rows = INITIAL_ROWS["INVENTARIO"]
        existing_rows = [desired_rows[0]]

        rows = _missing_rows(
            headers=headers,
            existing_rows=existing_rows,
            desired_rows=desired_rows,
            key_columns=["ID_ARTICOLO"],
        )

        self.assertEqual(len(rows), len(desired_rows) - 1)
        self.assertNotIn(desired_rows[0], rows)

    def test_dry_run_summary_is_offline_and_readable(self) -> None:
        summary = summarize_plan(build_resource_plan())

        self.assertIn("Modalità: DRY_RUN", summary)
        self.assertIn("ANAGRAFICA_ARTICOLI", summary)
        self.assertIn("Nessuna scrittura eseguita.", summary)

    def test_recipe_uses_four_trays_and_four_substrates_per_set(self) -> None:
        rows = INITIAL_ROWS["RICETTE_PRODUZIONE"]
        headers = RESOURCE_HEADERS["RICETTE_PRODUZIONE"]
        product_index = headers.index("PRODOTTO")
        article_index = headers.index("ID_ARTICOLO")
        quantity_index = headers.index("QUANTITA_PER_UNITA")

        by_product: dict[str, dict[str, str]] = {}
        for row in rows:
            by_product.setdefault(row[product_index], {})[row[article_index]] = row[quantity_index]

        for quantities in by_product.values():
            self.assertEqual(quantities["CON-VAS"], "4")
            self.assertEqual(quantities["SUB-COC"], "4")

    def test_inventory_is_reconciled_with_initial_movements(self) -> None:
        inventory_ids = {row[0] for row in INITIAL_ROWS["INVENTARIO"]}
        movement_article_ids = {row[2] for row in INITIAL_ROWS["MOVIMENTI_MAGAZZINO"]}

        self.assertEqual(inventory_ids, movement_article_ids)


if __name__ == "__main__":
    unittest.main()
