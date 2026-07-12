from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from src import process_event
from src.event_engine import (
    DEFAULT_TIMEZONE,
    EventDataContext,
    EventEngine,
    EventStatus,
    OperationalEvent,
    _load_schemas,
    build_demo_sheets,
)


def recurring_event(**overrides) -> OperationalEvent:
    data = {
        "event_id": "EVT-ORDER-TEST-001",
        "event_type": "NUOVO_ORDINE_RICORRENTE",
        "timestamp": "2026-09-01T10:00:00",
        "timezone": DEFAULT_TIMEZONE,
        "operatore": "Matteo",
        "source": "test",
        "status": "CONFERMATO",
        "payload": {
            "cliente": "Ristorante Buenaonda",
            "stato_cliente": "ATTIVO",
            "frequenza_giorni": 14,
            "giorno_consegna": "VENERDI",
            "prima_consegna": "2026-09-18",
            "prodotti": [
                {"varieta": "Basilico", "quantita": 1, "unita": "set"},
                {"varieta": "Amaranto", "quantita": 1, "unita": "set"},
                {"varieta": "Cilantro", "quantita": 1, "unita": "set"},
                {"varieta": "Finocchietto", "quantita": 1, "unita": "set"},
            ],
            "note": "Ordine ricorrente di test",
        },
    }
    for key, value in overrides.items():
        if key == "payload":
            data["payload"].update(value)
        else:
            data[key] = value
    return OperationalEvent.from_dict(data)


class RecurringOrderEventTest(unittest.TestCase):
    def setUp(self) -> None:
        self.schemas = _load_schemas(Path("docs/TPO_SHEETS_SCHEMA.md"))
        self.sheets = build_demo_sheets(self.schemas)
        self.engine = EventEngine.from_context(EventDataContext(self.sheets, self.schemas))

    def process(self, sheets=None, event=None):
        engine = EventEngine.from_context(EventDataContext(sheets or self.sheets, self.schemas))
        return engine.process(event or recurring_event())

    def add_client(self, sheets, client: str, status: str) -> None:
        headers = sheets["CLIENTI"].headers
        sheets["CLIENTI"].rows.append(
            {
                "CLIENTE": client,
                "FREQUENZA": "14",
                "GIORNO": "VENERDI",
                "STATO": status,
                "NOTE": "test",
            }
        )
        sheets["CLIENTI"].raw_values.append([sheets["CLIENTI"].rows[-1].get(header, "") for header in headers])

    def test_valid_recurring_order_generates_single_write_plan(self) -> None:
        result = self.process()

        self.assertTrue(result.success)
        self.assertEqual(result.status, EventStatus.PRONTO)
        self.assertIsNotNone(result.write_plan)
        self.assertEqual(len([result.write_plan]), 1)
        self.assertEqual(
            [operation.sheet_name for operation in result.write_plan.operations],
            ["CLIENTI", "CONSEGNE", "PIANO_SEMINE", "CALENDARIO_PRODUZIONE"],
        )

    def test_source_gate_not_passed_blocks_event(self) -> None:
        sheets = deepcopy(self.sheets)
        del sheets["STOCK"]

        result = self.process(sheets=sheets)

        self.assertFalse(result.success)
        self.assertIn("SOURCE_NOT_AVAILABLE", "\n".join(result.errors))
        self.assertIsNone(result.write_plan)

    def test_missing_client_creates_client_row(self) -> None:
        result = self.process()

        client_op = result.write_plan.operations[0]
        self.assertEqual(client_op.sheet_name, "CLIENTI")
        self.assertEqual(client_op.rows[0]["CLIENTE"], "Ristorante Buenaonda")

    def test_existing_active_client_is_not_duplicated(self) -> None:
        sheets = deepcopy(self.sheets)
        self.add_client(sheets, "Ristorante Buenaonda", "ATTIVO")

        result = self.process(sheets=sheets)

        self.assertTrue(result.success)
        self.assertNotIn("CLIENTI", [operation.sheet_name for operation in result.write_plan.operations])

    def test_suspended_client_blocks_order(self) -> None:
        sheets = deepcopy(self.sheets)
        self.add_client(sheets, "Ristorante Buenaonda", "SOSPESO")

        result = self.process(sheets=sheets)

        self.assertFalse(result.success)
        self.assertIn("Cliente sospeso", "\n".join(result.errors))

    def test_empty_products_are_blocked(self) -> None:
        result = self.process(event=recurring_event(payload={"prodotti": []}))

        self.assertFalse(result.success)
        self.assertIn("prodotti non può essere vuoto", "\n".join(result.errors))

    def test_zero_or_negative_quantity_is_blocked(self) -> None:
        result = self.process(event=recurring_event(payload={"prodotti": [{"varieta": "Basilico", "quantita": 0, "unita": "set"}]}))

        self.assertFalse(result.success)
        self.assertIn("quantita deve essere maggiore di zero", "\n".join(result.errors))

    def test_unit_different_from_set_is_blocked(self) -> None:
        result = self.process(event=recurring_event(payload={"prodotti": [{"varieta": "Basilico", "quantita": 1, "unita": "kg"}]}))

        self.assertFalse(result.success)
        self.assertIn("unita deve essere 'set'", "\n".join(result.errors))

    def test_invalid_frequency_is_blocked(self) -> None:
        result = self.process(event=recurring_event(payload={"frequenza_giorni": 0}))

        self.assertFalse(result.success)
        self.assertIn("frequenza_giorni deve essere maggiore di zero", "\n".join(result.errors))

    def test_non_iso_delivery_date_is_blocked(self) -> None:
        result = self.process(event=recurring_event(payload={"prima_consegna": "18/09/2026"}))

        self.assertFalse(result.success)
        self.assertIn("prima_consegna deve essere ISO", "\n".join(result.errors))

    def test_incompatible_weekday_is_blocked(self) -> None:
        result = self.process(event=recurring_event(payload={"prima_consegna": "2026-09-19"}))

        self.assertFalse(result.success)
        self.assertIn("giorno_consegna incompatibile", "\n".join(result.errors))

    def test_unknown_variety_is_blocked(self) -> None:
        result = self.process(event=recurring_event(payload={"prodotti": [{"varieta": "Shiso", "quantita": 1, "unita": "set"}]}))

        self.assertFalse(result.success)
        self.assertIn("Varietà non presente", "\n".join(result.errors))

    def test_missing_cycle_parameters_block_variety_and_plan(self) -> None:
        sheets = deepcopy(self.sheets)
        for row in sheets["MASTER_VARIETA"].rows:
            if row["VARIETA"] == "Basilico":
                row["TOTALE_GG"] = ""

        result = self.process(sheets=sheets, event=recurring_event(payload={"prodotti": [{"varieta": "Basilico", "quantita": 1, "unita": "set"}]}))

        self.assertFalse(result.success)
        self.assertIn("Parametri ciclo mancanti", "\n".join(result.errors))
        self.assertIsNone(result.write_plan)

    def test_duplicate_order_is_blocked(self) -> None:
        sheets = deepcopy(self.sheets)
        sheets["CONSEGNE"].rows.append(
            {
                "CLIENTE": "Ristorante Buenaonda",
                "PRODOTTO": "Basilico",
                "QUANTITA": "1",
                "UNITA": "set",
                "ID_LOTTO": "",
                "STATO": "ATTIVA",
                "GIORNO_CONSEGNA": "VENERDI",
                "FREQUENZA": "14",
                "PROSSIMA_CONSEGNA": "2026-09-18",
                "NOTE": "duplicato",
            }
        )

        result = self.process(sheets=sheets, event=recurring_event(payload={"prodotti": [{"varieta": "Basilico", "quantita": 1, "unita": "set"}]}))

        self.assertFalse(result.success)
        self.assertIn("Ordine duplicato", "\n".join(result.errors))

    def test_duplicate_order_with_italian_date_is_blocked(self) -> None:
        sheets = deepcopy(self.sheets)
        sheets["CONSEGNE"].rows.append(
            {
                "CLIENTE": "Ristorante Buenaonda",
                "PRODOTTO": "Basilico",
                "QUANTITA": "1",
                "UNITA": "set",
                "ID_LOTTO": "",
                "STATO": "ATTIVA",
                "GIORNO_CONSEGNA": "VENERDI",
                "FREQUENZA": "14",
                "PROSSIMA_CONSEGNA": "18/09/2026",
                "NOTE": "duplicato",
            }
        )

        result = self.process(sheets=sheets, event=recurring_event(payload={"prodotti": [{"varieta": "Basilico", "quantita": 1, "unita": "set"}]}))

        self.assertFalse(result.success)
        self.assertIn("Ordine duplicato", "\n".join(result.errors))

    def test_non_numeric_cycle_parameter_blocks_without_crash(self) -> None:
        sheets = deepcopy(self.sheets)
        for row in sheets["MASTER_VARIETA"].rows:
            if row["VARIETA"] == "Basilico":
                row["TOTALE_GG"] = "DA CONFERMARE"

        result = self.process(sheets=sheets, event=recurring_event(payload={"prodotti": [{"varieta": "Basilico", "quantita": 1, "unita": "set"}]}))

        self.assertFalse(result.success)
        self.assertIn("Parametri ciclo non numerici", "\n".join(result.errors))

    def test_insufficient_inventory_blocks_write_plan(self) -> None:
        sheets = deepcopy(self.sheets)
        for row in sheets["INVENTARIO"].rows:
            if row["ID_ARTICOLO"] == "SEM-BAS":
                row["QUANTITA_DISPONIBILE_REALE"] = "0"

        result = self.process(sheets=sheets, event=recurring_event(payload={"prodotti": [{"varieta": "Basilico", "quantita": 1, "unita": "set"}]}))

        self.assertFalse(result.success)
        self.assertIn("Inventario insufficiente", "\n".join(result.errors))
        self.assertIsNone(result.write_plan)

    def test_non_numeric_inventory_quantity_blocks_without_crash(self) -> None:
        sheets = deepcopy(self.sheets)
        for row in sheets["INVENTARIO"].rows:
            if row["ID_ARTICOLO"] == "SEM-BAS":
                row["QUANTITA_DISPONIBILE_REALE"] = "DA CONFERMARE"

        result = self.process(sheets=sheets, event=recurring_event(payload={"prodotti": [{"varieta": "Basilico", "quantita": 1, "unita": "set"}]}))

        self.assertFalse(result.success)
        self.assertIn("Quantità inventario non valida", "\n".join(result.errors))

    def test_multiple_varieties_have_calendar_preview(self) -> None:
        result = self.process()

        by_variety = {item["varieta"]: item for item in result.calendar_preview}
        self.assertEqual(by_variety["Basilico"]["data_semina"], "2026-09-08")
        self.assertEqual(by_variety["Cilantro"]["data_semina"], "2026-09-06")

    def test_no_future_lot_id_and_no_disallowed_operations(self) -> None:
        result = self.process()

        operation_names = [operation.sheet_name for operation in result.write_plan.operations]
        self.assertNotIn("STOCK", operation_names)
        self.assertNotIn("INVENTARIO", operation_names)
        self.assertNotIn("MOVIMENTI_MAGAZZINO", operation_names)
        calendar_op = next(operation for operation in result.write_plan.operations if operation.sheet_name == "CALENDARIO_PRODUZIONE")
        self.assertTrue(all(row["ID_LOTTO"] == "" for row in calendar_op.rows))

    def test_stock_delta_preview_does_not_create_stock_update(self) -> None:
        result = self.process()

        self.assertEqual(len(result.stock_delta_preview), 4)
        self.assertNotIn("STOCK", [operation.sheet_name for operation in result.write_plan.operations])

    def test_provenance_is_present(self) -> None:
        result = self.process()

        sources = {(item.source_type, item.source_name) for item in result.provenance}
        self.assertIn(("GOOGLE_SHEETS", "CLIENTI"), sources)
        self.assertIn(("GOOGLE_SHEETS", "RICETTE_PRODUZIONE"), sources)

    def test_cli_dry_run_for_recurring_order(self) -> None:
        handle = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json")
        json.dump(json.loads(Path("work/event_ordine_ricorrente.example.json").read_text(encoding="utf-8")), handle)
        handle.close()
        buffer = io.StringIO()

        with patch.object(sys, "argv", ["process_event", "--input", handle.name, "--dry-run"]):
            with patch("src.sheets_writer.SheetsWriter._write_log") as write_log:
                with redirect_stdout(buffer):
                    process_event.main()

        write_log.assert_not_called()
        output = buffer.getvalue()
        self.assertIn("Evento: NUOVO_ORDINE_RICORRENTE", output)
        self.assertIn("Ristorante Buenaonda", output)
        self.assertIn("Nessuna scrittura eseguita.", output)

if __name__ == "__main__":
    unittest.main()
