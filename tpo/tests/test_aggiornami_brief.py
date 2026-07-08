from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from src import aggiornami


def sample_report() -> dict:
    return {
        "dry_run": True,
        "document_source": "local",
        "google_sheets": "OK",
        "document_order": [
            "OPERATING_RULES.md",
            "TPO_SHEETS_SCHEMA.md",
            "AGENTS.md",
            "TPO_BOOTSTRAP.md",
        ],
        "schema_validation": [],
        "allarmi": [
            {
                "item": "rabano morado",
                "disponibile": "3",
                "prenotato": "4",
                "alarm": "ALLARME ROSSO",
                "priority": "PRIORITÀ ASSOLUTA",
            }
        ],
        "consegne": {
            "rows": [
                {
                    "CLIENTE": "",
                    "PRODOTTO": "",
                    "QUANTITÀ": "",
                    "UNITÀ": "",
                    "STATO": "",
                    "PROSSIMA_CONSEGNA": "",
                    "NOTE": "",
                },
                {
                    "CLIENTE": "Salvaje",
                    "PRODOTTO": "Rábano Morado",
                    "QUANTITÀ": "2",
                    "UNITÀ": "set",
                    "STATO": "Attiva",
                    "PROSSIMA_CONSEGNA": "09/07/2026",
                    "NOTE": "ordine standard",
                },
            ]
        },
        "lotti": {
            "rows": [
                {
                    "CALENDARIO_PROD": "RAB-3006-B",
                    "SET": "3",
                    "VARIETA": "rabano morado",
                    "DATA_SEMINA": "30/06/2026",
                    "DATA_PASSAGGIO": "05/07/2026",
                    "FASE": "luce",
                    "STATO": "ok",
                    "DATA_RACCOLTA": "09/07/2026",
                    "NOTE": "3 set produzione",
                }
            ]
        },
        "problemi": {
            "rows": [
                {
                    "DATA": "",
                    "AREA": "",
                    "GRAVITÀ": "",
                    "PROBLEMA": "",
                    "AZIONE_RICHIESTA": "",
                    "STATO": "",
                    "NOTE": "",
                },
                {
                    "AREA": "Pianificazione",
                    "GRAVITÀ": "CRITICA",
                    "PROBLEMA": "Stock rábano insufficiente",
                    "AZIONE_RICHIESTA": "Programmare produzione",
                    "STATO": "ALLARME ROSSO",
                    "NOTE": "Disponibile 3, prenotato 4",
                },
            ]
        },
        "stock": {
            "rows": [
                {
                    "VARIETÀ": "rabano morado",
                    "DISPONIBILE": "3",
                    "PRENOTATO": "4",
                    "VENDIBILE": "-1",
                }
            ]
        },
        "azioni_operative": [
            {
                "priority": "PRIORITÀ ASSOLUTA",
                "source": "STOCK",
                "action": "Programmare nuova produzione.",
            }
        ],
        "production_plan": {
            "idratazioni_da_fare": [
                {
                    "varieta": "rabano morado",
                    "set_da_produrre": "2",
                    "grammi_da_idratare": "28",
                    "motivo": "deficit stock 1 set + 1 set sicurezza",
                }
            ],
            "semine_da_fare": [],
            "passaggi_luce_da_fare": [],
            "raccolti_da_fare": [],
            "deficit_da_coprire": [],
            "note_operatore": [],
        },
    }


class AggiornamiBriefTest(unittest.TestCase):
    def test_human_output_contains_title(self) -> None:
        output = aggiornami.format_human_brief(sample_report())

        self.assertIn("TOWER POWER OPERATIONS", output)

    def test_human_output_contains_absolute_priority(self) -> None:
        output = aggiornami.format_human_brief(sample_report())

        self.assertIn("PRIORITÀ ASSOLUTA", output)

    def test_human_output_ignores_empty_rows(self) -> None:
        output = aggiornami.format_human_brief(sample_report())

        self.assertNotIn("•  —", output)
        self.assertNotIn("Problema: \n", output)

    def test_json_flag_still_prints_json(self) -> None:
        buffer = io.StringIO()
        with patch.object(sys, "argv", ["aggiornami", "--json"]):
            with patch.object(aggiornami, "build_report", return_value=sample_report()):
                with redirect_stdout(buffer):
                    aggiornami.main()

        parsed = json.loads(buffer.getvalue())
        self.assertEqual(parsed["document_source"], "local")
        self.assertEqual(parsed["allarmi"][0]["item"], "rabano morado")
        self.assertIn("production_plan", parsed)

    def test_human_output_contains_production_plan(self) -> None:
        output = aggiornami.format_human_brief(sample_report())

        self.assertIn("PIANO PRODUZIONE", output)

    def test_empty_schema_validation_shows_ok(self) -> None:
        report = sample_report()
        report["schema_validation"] = []

        output = aggiornami.format_human_brief(report)

        self.assertIn("Schema: OK", output)

    def test_schema_validation_with_items_shows_errors(self) -> None:
        report = sample_report()
        report["schema_validation"] = [
            {
                "sheet_name": "STOCK",
                "level": "ERROR",
                "message": "Intestazione mancante",
            }
        ]

        output = aggiornami.format_human_brief(report)

        self.assertIn("Schema: errori", output)


if __name__ == "__main__":
    unittest.main()
