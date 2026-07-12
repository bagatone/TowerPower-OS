from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from src.event_engine import (
    DEFAULT_TIMEZONE,
    EventDataContext,
    EventEngine,
    EventStatus,
    OperationalEvent,
    build_demo_sheets,
    _load_schemas,
)
from src.sheets_loader import SheetData
from src.source_gate import build_google_sheets_provenance


def valid_event(**overrides):
    data = {
        "event_id": "EVT-TEST-001",
        "event_type": "SEMINA",
        "timestamp": "2026-07-10T16:00:00",
        "timezone": DEFAULT_TIMEZONE,
        "operatore": "Matteo",
        "source": "test",
        "status": "CONFERMATO",
        "payload": {
            "varieta": "Cilantro",
            "set": 6,
            "unita": "set",
            "data_semina": "2026-07-10",
            "id_lotto": "CIL-TEST-001",
            "note": "Test",
        },
    }
    for key, value in overrides.items():
        if key == "payload":
            data["payload"].update(value)
        else:
            data[key] = value
    return OperationalEvent.from_dict(data)


class EventEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.schemas = _load_schemas(Path("docs/TPO_SHEETS_SCHEMA.md"))
        self.sheets = build_demo_sheets(self.schemas)
        self.engine = EventEngine.from_context(EventDataContext(self.sheets, self.schemas))

    def test_valid_semina_event_generates_write_plan(self) -> None:
        result = self.engine.process(valid_event())

        self.assertTrue(result.success)
        self.assertEqual(result.status, EventStatus.PRONTO)
        self.assertEqual([op.sheet_name for op in result.write_plan.operations], ["SEMINE", "LOTTI", "MOVIMENTI_MAGAZZINO"])

    def test_generates_one_write_plan(self) -> None:
        result = self.engine.process(valid_event())

        self.assertIsNotNone(result.write_plan)
        self.assertEqual(len([result.write_plan]), 1)

    def test_engine_does_not_write_directly(self) -> None:
        with patch("src.sheets_writer.SheetsWriter.dry_run") as dry_run:
            with patch("src.sheets_writer.SheetsWriter.apply") as apply:
                result = self.engine.process(valid_event())

        self.assertTrue(result.success)
        dry_run.assert_not_called()
        apply.assert_not_called()

    def test_unsupported_event_is_blocked(self) -> None:
        result = self.engine.process(valid_event(event_type="RACCOLTA"))

        self.assertFalse(result.success)
        self.assertIn("event_type non supportato", result.errors[0])

    def test_missing_event_id_is_blocked(self) -> None:
        result = self.engine.process(valid_event(event_id=""))

        self.assertFalse(result.success)
        self.assertIn("event_id mancante", result.errors[0])

    def test_missing_varieta_is_blocked(self) -> None:
        result = self.engine.process(valid_event(payload={"varieta": ""}))

        self.assertFalse(result.success)
        self.assertIn("Campi obbligatori mancanti", result.errors[0])

    def test_zero_set_is_blocked(self) -> None:
        result = self.engine.process(valid_event(payload={"set": 0}))

        self.assertFalse(result.success)
        self.assertIn("maggiore di zero", "\n".join(result.errors))

    def test_negative_set_is_blocked(self) -> None:
        result = self.engine.process(valid_event(payload={"set": -1}))

        self.assertFalse(result.success)
        self.assertIn("maggiore di zero", "\n".join(result.errors))

    def test_wrong_unit_is_blocked(self) -> None:
        result = self.engine.process(valid_event(payload={"unita": "kg"}))

        self.assertFalse(result.success)
        self.assertIn("unita deve essere", "\n".join(result.errors))

    def test_invalid_date_is_blocked(self) -> None:
        result = self.engine.process(valid_event(payload={"data_semina": "10/07/2026"}))

        self.assertFalse(result.success)
        self.assertIn("data_semina deve essere ISO", "\n".join(result.errors))

    def test_impossible_iso_date_is_blocked(self) -> None:
        result = self.engine.process(valid_event(payload={"data_semina": "2026-99-99"}))

        self.assertFalse(result.success)
        self.assertIn("data_semina deve essere una data ISO valida", "\n".join(result.errors))

    def test_wrong_timezone_is_blocked(self) -> None:
        result = self.engine.process(valid_event(timezone="Europe/Rome"))

        self.assertFalse(result.success)
        self.assertIn("timezone non valida", "\n".join(result.errors))

    def test_missing_lot_id_is_blocked(self) -> None:
        result = self.engine.process(valid_event(payload={"id_lotto": ""}))

        self.assertFalse(result.success)
        self.assertIn("ID_LOTTO mancante", "\n".join(result.errors))

    def test_duplicate_lot_id_is_blocked(self) -> None:
        sheets = deepcopy(self.sheets)
        headers = sheets["SEMINE"].headers
        row = dict.fromkeys(headers, "")
        row["ID_LOTTO"] = "CIL-TEST-001"
        sheets["SEMINE"].rows.append(row)
        engine = EventEngine.from_context(EventDataContext(sheets, self.schemas))

        result = engine.process(valid_event())

        self.assertFalse(result.success)
        self.assertIn("ID_LOTTO già presente", "\n".join(result.errors))

    def test_duplicate_lot_id_in_lotti_is_blocked(self) -> None:
        sheets = deepcopy(self.sheets)
        headers = sheets["LOTTI"].headers
        row = dict.fromkeys(headers, "")
        row["CALENDARIO_PROD"] = "CIL-TEST-001"
        sheets["LOTTI"].rows.append(row)
        engine = EventEngine.from_context(EventDataContext(sheets, self.schemas))

        result = engine.process(valid_event())

        self.assertFalse(result.success)
        self.assertIn("ID_LOTTO già presente", "\n".join(result.errors))

    def test_unknown_variety_is_blocked(self) -> None:
        result = self.engine.process(valid_event(payload={"varieta": "Basilico Genovese"}))

        self.assertFalse(result.success)
        self.assertIn("Varietà non presente", "\n".join(result.errors))

    def test_missing_recipe_is_blocked(self) -> None:
        sheets = deepcopy(self.sheets)
        headers = sheets["RICETTE_PRODUZIONE"].headers
        sheets["RICETTE_PRODUZIONE"] = SheetData(
            "RICETTE_PRODUZIONE",
            headers,
            [],
            [headers],
            provenance=build_google_sheets_provenance(
                "RICETTE_PRODUZIONE",
                "test",
                [headers],
            ),
        )
        engine = EventEngine.from_context(EventDataContext(sheets, self.schemas))

        result = engine.process(valid_event())

        self.assertFalse(result.success)
        self.assertIn("Ricetta mancante", "\n".join(result.errors))

    def test_insufficient_inventory_is_blocked(self) -> None:
        sheets = deepcopy(self.sheets)
        for row in sheets["INVENTARIO"].rows:
            if row["ID_ARTICOLO"] == "CON-VAS":
                row["QUANTITA_DISPONIBILE_REALE"] = "1"
        engine = EventEngine.from_context(EventDataContext(sheets, self.schemas))

        result = engine.process(valid_event())

        self.assertFalse(result.success)
        self.assertIn("Inventario insufficiente", "\n".join(result.errors))

    def test_consumption_is_calculated_for_multiple_sets(self) -> None:
        result = self.engine.process(valid_event())

        by_article = {item["id_articolo"]: item for item in result.consumi}
        self.assertEqual(by_article["SEM-CIL"]["quantita"], "84")
        self.assertEqual(by_article["CON-VAS"]["quantita"], "24")
        self.assertEqual(by_article["SUB-COC"]["quantita"], "24")

    def test_write_plan_contains_resource_movements(self) -> None:
        result = self.engine.process(valid_event())
        movements = next(op for op in result.write_plan.operations if op.sheet_name == "MOVIMENTI_MAGAZZINO")

        self.assertEqual(len(movements.rows), 3)
        self.assertTrue(all(row["TIPO_MOVIMENTO"] == "USCITA_PRODUZIONE" for row in movements.rows))

    def test_invalid_sheet_structure_is_blocked(self) -> None:
        sheets = deepcopy(self.sheets)
        sheets["SEMINE"] = SheetData(
            "SEMINE",
            ["ID_LOTTO"],
            [],
            [["ID_LOTTO"]],
            provenance=build_google_sheets_provenance(
                "SEMINE",
                "test",
                [["ID_LOTTO"]],
            ),
        )
        engine = EventEngine.from_context(EventDataContext(sheets, self.schemas))

        result = engine.process(valid_event())

        self.assertFalse(result.success)
        self.assertIn("SEMINE: intestazioni non valide", "\n".join(result.errors))


if __name__ == "__main__":
    unittest.main()
