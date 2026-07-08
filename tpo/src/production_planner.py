from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any


CLOSED_STATUSES = {"CHIUSO", "FALLITO", "RACCOLTO", "RISOLTO", "CLOSED", "DONE"}


def build_production_plan(report: dict) -> dict:
    today = date.today()
    master_index = _build_master_index(report.get("master_varieta", {}).get("rows", []))
    plan = {
        "idratazioni_da_fare": [],
        "semine_da_fare": [],
        "passaggi_luce_da_fare": [],
        "raccolti_da_fare": [],
        "deficit_da_coprire": [],
        "note_operatore": [],
    }

    _add_deficit_actions(report, master_index, plan)
    _add_lot_actions(report, master_index, plan, today)
    return plan


def _add_deficit_actions(
    report: dict,
    master_index: dict[str, dict[str, Any]],
    plan: dict[str, list],
) -> None:
    for row in report.get("stock", {}).get("rows", []):
        if not _has_content(row):
            continue
        disponibile = _decimal(row.get("DISPONIBILE"))
        prenotato = _decimal(row.get("PRENOTATO"))
        if disponibile >= prenotato:
            continue

        variety = _variety(row)
        deficit = prenotato - disponibile
        set_to_produce = deficit + Decimal("1")
        deficit_entry = {
            "varieta": variety,
            "disponibile": disponibile,
            "prenotato": prenotato,
            "deficit": deficit,
            "set_da_produrre": set_to_produce,
            "motivo": f"deficit stock {_fmt_number(deficit)} set + 1 set sicurezza",
        }
        plan["deficit_da_coprire"].append(deficit_entry)

        master = master_index.get(_canonical(variety))
        if not master:
            plan["note_operatore"].append(
                f"Varietà non presente in MASTER_VARIETA: {variety}"
            )
            continue

        grams_per_set = _decimal(master.get("GRAMMI_SET"))
        hydration_hours = _decimal(master.get("IDRATAZIONE_ORE"))
        grams_to_hydrate = set_to_produce * grams_per_set
        action = {
            "varieta": variety,
            "set_da_produrre": set_to_produce,
            "grammi_da_idratare": grams_to_hydrate,
            "grammi_set": grams_per_set,
            "idratazione_ore": hydration_hours,
            "motivo": deficit_entry["motivo"],
        }
        if hydration_hours > 0:
            plan["idratazioni_da_fare"].append(action)
        else:
            plan["semine_da_fare"].append(
                {
                    **action,
                    "azione": "Semina diretta oggi",
                }
            )


def _add_lot_actions(
    report: dict,
    master_index: dict[str, dict[str, Any]],
    plan: dict[str, list],
    today: date,
) -> None:
    for row in report.get("lotti", {}).get("rows", []):
        if not _has_content(row):
            continue
        status = str(row.get("STATO", "")).strip().upper()
        if status in CLOSED_STATUSES:
            continue

        phase = str(row.get("FASE", "")).strip().lower()
        variety = _variety(row)
        master = master_index.get(_canonical(variety))
        if not master:
            plan["note_operatore"].append(
                f"Varietà non presente in MASTER_VARIETA: {variety}"
            )
            continue

        sowing_date = _parse_date(row.get("DATA_SEMINA"))
        if not sowing_date:
            continue

        lot_id = row.get("CALENDARIO_PROD") or row.get("ID_LOTTO") or ""
        germination_days = int(_decimal(master.get("GERMINAZIONE_GG")))
        total_days = int(_decimal(master.get("TOTALE_GG")))

        if phase == "germinazione" and today >= sowing_date + timedelta(days=germination_days):
            plan["passaggi_luce_da_fare"].append(
                {
                    "id_lotto": lot_id,
                    "varieta": variety,
                    "seminato": sowing_date.isoformat(),
                    "fase": row.get("FASE", ""),
                    "stato": row.get("STATO", ""),
                    "azione": "valutare passaggio a luce",
                }
            )
        elif phase == "luce" and today >= sowing_date + timedelta(days=total_days):
            plan["raccolti_da_fare"].append(
                {
                    "id_lotto": lot_id,
                    "varieta": variety,
                    "seminato": sowing_date.isoformat(),
                    "fase": row.get("FASE", ""),
                    "stato": row.get("STATO", ""),
                    "azione": "raccolta prevista oggi",
                    "destinazione_possibile": "consegne attive / stock",
                }
            )


def _build_master_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not _has_content(row):
            continue
        variety = _variety(row)
        if variety:
            index[_canonical(variety)] = row
    return index


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _decimal(value: Any) -> Decimal:
    normalized = str(value or "").strip().replace(",", ".")
    if not normalized:
        return Decimal("0")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return Decimal("0")


def _variety(row: dict[str, Any]) -> str:
    return str(row.get("VARIETA") or row.get("VARIETÀ") or row.get("PRODOTTO") or "").strip()


def _canonical(value: Any) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", str(value))
        if not unicodedata.combining(char)
    )
    return re.sub(r"[\s_]+", "", without_accents).upper()


def _fmt_number(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(value.quantize(Decimal("1")))
    return str(value.normalize())


def _has_content(row: dict[str, Any]) -> bool:
    return any(str(value).strip() for value in row.values())
