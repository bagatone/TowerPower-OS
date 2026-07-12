from __future__ import annotations

import unittest
from decimal import Decimal

from src.production_planner import build_production_plan
from src.source_gate import build_google_sheets_provenance


def report_for_planner() -> dict:
    report = {
        "stock": {
            "rows": [
                {
                    "VARIETÀ": "rábano morado",
                    "DISPONIBILE": "3",
                    "PRENOTATO": "4",
                    "VENDIBILE": "-1",
                },
                {
                    "VARIETÀ": "hinojo",
                    "DISPONIBILE": "0",
                    "PRENOTATO": "1",
                    "VENDIBILE": "-1",
                },
            ]
        },
        "master_varieta": {
            "rows": [
                {
                    "VARIETA": "rabano morado",
                    "GRAMMI_SET": "14",
                    "IDRATAZIONE_ORE": "8",
                    "GERMINAZIONE_GG": "5",
                    "LUCE_GG": "4",
                    "TOTALE_GG": "9",
                },
                {
                    "VARIETA": "hinojo",
                    "GRAMMI_SET": "3",
                    "IDRATAZIONE_ORE": "0",
                    "GERMINAZIONE_GG": "1",
                    "LUCE_GG": "5",
                    "TOTALE_GG": "6",
                },
                {
                    "VARIETA": "guisante afila",
                    "GRAMMI_SET": "30",
                    "IDRATAZIONE_ORE": "12",
                    "GERMINAZIONE_GG": "1",
                    "LUCE_GG": "5",
                    "TOTALE_GG": "6",
                },
                {
                    "VARIETA": "cilantro",
                    "GRAMMI_SET": "14",
                    "IDRATAZIONE_ORE": "12",
                    "GERMINAZIONE_GG": "5",
                    "LUCE_GG": "4",
                    "TOTALE_GG": "9",
                },
            ]
        },
        "lotti": {
            "rows": [
                {
                    "CALENDARIO_PROD": "AFI-OLD-A",
                    "VARIETA": "guisante afila",
                    "DATA_SEMINA": "01/01/2000",
                    "FASE": "germinazione",
                    "STATO": "ok",
                },
                {
                    "CALENDARIO_PROD": "CIL-OLD-A",
                    "VARIETA": "cilantro",
                    "DATA_SEMINA": "01/01/2000",
                    "FASE": "luce",
                    "STATO": "ok",
                },
                {
                    "CALENDARIO_PROD": "RAB-CLOSED-A",
                    "VARIETA": "rabano morado",
                    "DATA_SEMINA": "01/01/2000",
                    "FASE": "luce",
                    "STATO": "chiuso",
                },
            ]
        },
    }
    report["provenance"] = {
        "sheets": {
            sheet_name: build_google_sheets_provenance(
                sheet_name,
                "test",
                [[sheet_name]],
            ).to_dict()
            for sheet_name in [
                "PIANO_SEMINE",
                "CALENDARIO_PRODUZIONE",
                "MASTER_VARIETA",
                "CONSEGNE",
                "STOCK",
            ]
        }
    }
    return report


class ProductionPlannerTest(unittest.TestCase):
    def test_deficit_rabano_generates_production(self) -> None:
        plan = build_production_plan(report_for_planner())

        rabano = plan["deficit_da_coprire"][0]
        self.assertEqual(rabano["varieta"], "rábano morado")
        self.assertEqual(rabano["deficit"], Decimal("1"))
        self.assertEqual(rabano["set_da_produrre"], Decimal("2"))

    def test_grams_are_calculated_from_master_varieta(self) -> None:
        plan = build_production_plan(report_for_planner())

        rabano_hydration = plan["idratazioni_da_fare"][0]
        self.assertEqual(rabano_hydration["grammi_da_idratare"], Decimal("28"))

    def test_hydration_when_hydration_hours_is_positive(self) -> None:
        plan = build_production_plan(report_for_planner())

        varieties = [item["varieta"] for item in plan["idratazioni_da_fare"]]
        self.assertIn("rábano morado", varieties)

    def test_direct_sowing_when_hydration_hours_is_zero(self) -> None:
        plan = build_production_plan(report_for_planner())

        varieties = [item["varieta"] for item in plan["semine_da_fare"]]
        self.assertIn("hinojo", varieties)

    def test_light_move_from_germination(self) -> None:
        plan = build_production_plan(report_for_planner())

        lot_ids = [item["id_lotto"] for item in plan["passaggi_luce_da_fare"]]
        self.assertIn("AFI-OLD-A", lot_ids)

    def test_harvest_from_light_phase(self) -> None:
        plan = build_production_plan(report_for_planner())

        lot_ids = [item["id_lotto"] for item in plan["raccolti_da_fare"]]
        self.assertIn("CIL-OLD-A", lot_ids)
        self.assertNotIn("RAB-CLOSED-A", lot_ids)


if __name__ == "__main__":
    unittest.main()
