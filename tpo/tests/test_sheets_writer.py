from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.sheets_writer import SheetsWriter, WritePlan


class FakeExecute:
    def __init__(self, value=None, callback=None):
        self.value = value
        self.callback = callback

    def execute(self):
        if self.callback:
            self.callback()
        return self.value


class FakeValues:
    def __init__(self, service):
        self.service = service

    def get(self, spreadsheetId, range):
        sheet_name = range.split("!", 1)[0]
        if sheet_name not in self.service.sheets:
            raise RuntimeError("Unable to parse range")
        return FakeExecute({"values": self.service.sheets[sheet_name]})

    def batchUpdate(self, spreadsheetId, body):
        def callback():
            self.service.batch_update_calls += 1
            for item in body.get("data", []):
                sheet_name = item["range"].split("!", 1)[0]
                self.service.sheets[sheet_name].extend(item.get("values", []))

        return FakeExecute({"updatedRows": 1}, callback)


class FakeSpreadsheets:
    def __init__(self, service):
        self.service = service

    def values(self):
        return FakeValues(self.service)


class FakeService:
    def __init__(self, sheets):
        self.sheets = sheets
        self.batch_update_calls = 0

    def spreadsheets(self):
        return FakeSpreadsheets(self)


class SheetsWriterTest(unittest.TestCase):
    def writer(self, sheets):
        return SheetsWriter(spreadsheet_id="test", service=FakeService(sheets))

    def test_values_are_ordered_and_missing_columns_are_empty(self) -> None:
        writer = self.writer({"FORNITORI": [["ID_FORNITORE", "RAGIONE_SOCIALE", "CONTATTO", "EMAIL", "TELEFONO", "SITO_WEB", "TEMPO_CONSEGNA_GG", "STATO", "NOTE"]]})
        plan = WritePlan.from_dict(
            {
                "operations": [
                    {
                        "sheet_name": "FORNITORI",
                        "mode": "append",
                        "rows": [{"STATO": "ATTIVO", "ID_FORNITORE": "F-001"}],
                    }
                ]
            }
        )

        result = writer.apply(plan)

        self.assertTrue(result.success)
        self.assertEqual(
            writer.service.sheets["FORNITORI"][1],
            ["F-001", "", "", "", "", "", "", "ATTIVO", ""],
        )

    def test_unknown_columns_are_rejected(self) -> None:
        writer = self.writer({"FORNITORI": [["ID_FORNITORE", "RAGIONE_SOCIALE", "CONTATTO", "EMAIL", "TELEFONO", "SITO_WEB", "TEMPO_CONSEGNA_GG", "STATO", "NOTE"]]})
        plan = WritePlan.from_dict(
            {
                "operations": [
                    {
                        "sheet_name": "FORNITORI",
                        "mode": "append",
                        "rows": [{"ID_FORNITORE": "F-001", "COLONNA_FALSA": "x"}],
                    }
                ]
            }
        )

        result = writer.dry_run(plan)

        self.assertFalse(result.success)
        self.assertIn("colonne sconosciute", result.errors[0])

    def test_empty_rows_are_rejected(self) -> None:
        writer = self.writer({"FORNITORI": [["ID_FORNITORE", "RAGIONE_SOCIALE", "CONTATTO", "EMAIL", "TELEFONO", "SITO_WEB", "TEMPO_CONSEGNA_GG", "STATO", "NOTE"]]})
        plan = WritePlan.from_dict(
            {"operations": [{"sheet_name": "FORNITORI", "mode": "append", "rows": [{}]}]}
        )

        result = writer.dry_run(plan)

        self.assertFalse(result.success)
        self.assertIn("riga completamente vuota", result.errors[0])

    def test_duplicates_are_detected(self) -> None:
        writer = self.writer({"FORNITORI": [["ID_FORNITORE", "RAGIONE_SOCIALE", "CONTATTO", "EMAIL", "TELEFONO", "SITO_WEB", "TEMPO_CONSEGNA_GG", "STATO", "NOTE"], ["F-001", "Gia presente"]]})
        plan = WritePlan.from_dict(
            {
                "operations": [
                    {
                        "sheet_name": "FORNITORI",
                        "mode": "append",
                        "rows": [{"ID_FORNITORE": "F-001"}],
                    }
                ]
            }
        )

        result = writer.dry_run(plan)

        self.assertFalse(result.success)
        self.assertEqual(len(result.duplicates["FORNITORI"]), 1)

    def test_invalid_operation_blocks_whole_plan(self) -> None:
        writer = self.writer(
            {
                "FORNITORI": [["ID_FORNITORE", "RAGIONE_SOCIALE", "CONTATTO", "EMAIL", "TELEFONO", "SITO_WEB", "TEMPO_CONSEGNA_GG", "STATO", "NOTE"]],
                "ANAGRAFICA_ARTICOLI": [["ID_ARTICOLO", "CATEGORIA", "ARTICOLO", "VARIANTE", "UNITA_MISURA", "TRACCIABILE", "CONSERVAZIONE", "SCADENZA_GESTITA", "UTILIZZO", "STATO", "NOTE"]],
            }
        )
        plan = WritePlan.from_dict(
            {
                "operations": [
                    {"sheet_name": "FORNITORI", "mode": "append", "rows": [{"ID_FORNITORE": "F-001"}]},
                    {"sheet_name": "ANAGRAFICA_ARTICOLI", "mode": "append", "rows": [{"COLONNA_FALSA": "x"}]},
                ]
            }
        )

        result = writer.apply(plan)

        self.assertFalse(result.success)
        self.assertEqual(writer.service.batch_update_calls, 0)

    def test_dry_run_does_not_write(self) -> None:
        writer = self.writer({"FORNITORI": [["ID_FORNITORE", "RAGIONE_SOCIALE", "CONTATTO", "EMAIL", "TELEFONO", "SITO_WEB", "TEMPO_CONSEGNA_GG", "STATO", "NOTE"]]})
        plan = WritePlan.from_dict(
            {"operations": [{"sheet_name": "FORNITORI", "mode": "append", "rows": [{"ID_FORNITORE": "F-001"}]}]}
        )

        result = writer.dry_run(plan)

        self.assertTrue(result.success)
        self.assertEqual(writer.service.batch_update_calls, 0)

    def test_apply_writes_only_after_valid_preflight(self) -> None:
        writer = self.writer({"FORNITORI": [["ID_FORNITORE", "RAGIONE_SOCIALE", "CONTATTO", "EMAIL", "TELEFONO", "SITO_WEB", "TEMPO_CONSEGNA_GG", "STATO", "NOTE"]]})
        plan = WritePlan.from_dict(
            {"operations": [{"sheet_name": "FORNITORI", "mode": "append", "rows": [{"ID_FORNITORE": "F-001"}]}]}
        )

        result = writer.apply(plan)

        self.assertTrue(result.success)
        self.assertEqual(writer.service.batch_update_calls, 1)

    def test_multiple_sheets_in_same_plan(self) -> None:
        writer = self.writer(
            {
                "FORNITORI": [["ID_FORNITORE", "RAGIONE_SOCIALE", "CONTATTO", "EMAIL", "TELEFONO", "SITO_WEB", "TEMPO_CONSEGNA_GG", "STATO", "NOTE"]],
                "ANAGRAFICA_ARTICOLI": [["ID_ARTICOLO", "CATEGORIA", "ARTICOLO", "VARIANTE", "UNITA_MISURA", "TRACCIABILE", "CONSERVAZIONE", "SCADENZA_GESTITA", "UTILIZZO", "STATO", "NOTE"]],
            }
        )
        plan = WritePlan.from_dict(
            {
                "operations": [
                    {"sheet_name": "FORNITORI", "mode": "append", "rows": [{"ID_FORNITORE": "F-001"}]},
                    {"sheet_name": "ANAGRAFICA_ARTICOLI", "mode": "append", "rows": [{"ID_ARTICOLO": "ART-001"}]},
                ]
            }
        )

        result = writer.dry_run(plan)

        self.assertTrue(result.success)
        self.assertEqual(result.rows_valid["FORNITORI"], 1)
        self.assertEqual(result.rows_valid["ANAGRAFICA_ARTICOLI"], 1)

    def test_multiple_operations_on_same_sheet_are_merged_for_apply(self) -> None:
        writer = self.writer({"FORNITORI": [["ID_FORNITORE", "RAGIONE_SOCIALE", "CONTATTO", "EMAIL", "TELEFONO", "SITO_WEB", "TEMPO_CONSEGNA_GG", "STATO", "NOTE"]]})
        plan = WritePlan.from_dict(
            {
                "operations": [
                    {"sheet_name": "FORNITORI", "mode": "append", "rows": [{"ID_FORNITORE": "F-001"}]},
                    {"sheet_name": "FORNITORI", "mode": "append", "rows": [{"ID_FORNITORE": "F-002"}]},
                ]
            }
        )

        result = writer.apply(plan)

        self.assertTrue(result.success)
        self.assertEqual(result.rows_written["FORNITORI"], 2)
        self.assertEqual(writer.service.batch_update_calls, 1)
        self.assertEqual(len(writer.service.sheets["FORNITORI"]), 3)

    def test_unconfigured_dedup_key_blocks_apply(self) -> None:
        writer = self.writer({"PIANO_EXTRA": [["DATA_CICLO", "VARIETA", "SET_EXTRA", "MOTIVO", "CONFERMATO", "NOTE"]]})
        plan = WritePlan.from_dict(
            {"operations": [{"sheet_name": "PIANO_EXTRA", "mode": "append", "rows": [{"DATA_CICLO": "oggi"}]}]}
        )

        result = writer.apply(plan)

        self.assertFalse(result.success)
        self.assertIn("chiave di deduplicazione non configurata", result.errors[0])


if __name__ == "__main__":
    unittest.main()
