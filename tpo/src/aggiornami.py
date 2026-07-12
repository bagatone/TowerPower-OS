from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .config_loader import load_config
from .document_provider import (
    MissingDocumentError,
    RepositoryNotFoundError,
    build_document_provider,
)
from .production_planner import build_production_plan
from .row_generator import RowGenerator
from .schema_validator import SchemaValidator
from .sheets_loader import SheetsLoader, SheetsLoaderError
from .source_gate import SourceGate, SourceGateError, SourceNotAvailableError, provenance_report
from .stock_alarm import StockAlarmEngine


SECTIONS = [
    "allarmi",
    "stock",
    "consegne",
    "lotti",
    "semine",
    "problemi",
    "azioni_operative",
]

LINE = "═══════════════════════════════════════"
SECTION_LINE = "───────────────────────────────────────"


def build_report(config_path: str | Path = "config/settings.yaml") -> dict[str, Any]:
    load_dotenv()
    config = load_config(config_path)
    if config.get("dry_run") is not True:
        raise RuntimeError("La prima versione deve girare con DRY_RUN = TRUE.")

    document_provider = build_document_provider(config)
    documents = document_provider.load_documents()
    source_gate = SourceGate.from_config(config)
    source_gate.assert_documents(documents)

    schema_markdown = documents["TPO_SHEETS_SCHEMA.md"].content
    validator = SchemaValidator()
    schemas = validator.parse_schema(schema_markdown)
    expected_headers = {
        sheet_name: schema.headers for sheet_name, schema in schemas.items()
    }

    sheets_loader = SheetsLoader.from_config(config)
    required_sheets = config.get("google_sheets", {}).get("sheets")
    sheets = sheets_loader.load_required_sheets(
        required_sheets,
        expected_headers=expected_headers,
    )
    source_gate.assert_sheets(sheets)
    source_gate_result = source_gate.enforce_request("aggiornami", sheets)
    validation_issues = validator.validate(sheets, schemas)

    stock_sheet = sheets.get("STOCK")
    alarms = StockAlarmEngine().evaluate(stock_sheet) if stock_sheet else []
    actions = RowGenerator().build_operational_actions(
        alarms=alarms,
        problems=sheets.get("PROBLEMI").rows if sheets.get("PROBLEMI") else [],
    )

    report = {
        "dry_run": True,
        "document_source": str(config.get("document_source", "github")).lower(),
        "google_sheets": "OK",
        "document_order": list(documents.keys()),
        "status": "OK",
        "source_gate": source_gate_result.to_dict(),
        "provenance": {
            "documents": provenance_report(documents),
            "sheets": provenance_report(sheets),
        },
        "schema_validation": [asdict(issue) for issue in validation_issues],
        "allarmi": [asdict(alarm) for alarm in alarms],
        "stock": _sheet_preview(sheets.get("STOCK")),
        "consegne": _sheet_preview(sheets.get("CONSEGNE"), sort_key=_delivery_sort_key),
        "lotti": _sheet_preview(sheets.get("LOTTI")),
        "semine": _sheet_preview(sheets.get("SEMINE")),
        "master_varieta": _sheet_preview(sheets.get("MASTER_VARIETA")),
        "piano_semine": _sheet_preview(sheets.get("PIANO_SEMINE")),
        "problemi": _sheet_preview(sheets.get("PROBLEMI")),
        "azioni_operative": actions,
    }
    report["production_plan"] = build_production_plan(report)
    return report


def _sheet_preview(sheet, limit: int = 20, sort_key=None) -> dict[str, Any]:
    if not sheet:
        return {"headers": [], "rows": []}
    rows = sorted(sheet.rows, key=sort_key) if sort_key else sheet.rows
    return {"headers": sheet.headers, "rows": rows[:limit], "total_rows": len(sheet.rows)}


def _delivery_sort_key(row: dict[str, Any]) -> tuple[str, str]:
    raw_date = str(row.get("PROSSIMA_CONSEGNA", "")).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            normalized = datetime.strptime(raw_date[:10], fmt).strftime("%Y-%m-%d")
            break
        except ValueError:
            normalized = raw_date or "9999-99-99"
    return (normalized, str(row.get("CLIENTE", "")))


def format_human_brief(report: dict[str, Any]) -> str:
    lines = [
        LINE,
        "🌱 TOWER POWER OPERATIONS",
        "AGGIORNAMI",
        f"Data/Ora: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Modalità: {'DRY RUN' if report.get('dry_run') else 'LIVE'}",
        LINE,
        "",
        "🔴 PRIORITÀ ASSOLUTA",
        "",
    ]

    alarms = report.get("allarmi", [])
    if alarms:
        for alarm in alarms:
            disponibile = _decimal(alarm.get("disponibile"))
            prenotato = _decimal(alarm.get("prenotato"))
            deficit = prenotato - disponibile
            lines.extend(
                [
                    f"• {_title(alarm.get('item', 'Varietà non specificata'))}",
                    f"  Disponibile: {_fmt_number(disponibile)} set",
                    f"  Prenotato: {_fmt_number(prenotato)} set",
                    f"  Deficit: {_fmt_number(deficit)} set",
                    "  Azione: programmare nuova produzione immediata.",
                ]
            )
    else:
        lines.append("Nessun allarme stock.")

    lines.extend(["", SECTION_LINE, "", "📦 CONSEGNE ATTIVE", ""])
    lines.extend(_format_consegne(report.get("consegne", {}).get("rows", [])))

    lines.extend(["", SECTION_LINE, "", "🌱 LOTTI", ""])
    lines.extend(_format_lotti(report.get("lotti", {}).get("rows", [])))

    lines.extend(["", SECTION_LINE, "", "🧠 PIANO PRODUZIONE", ""])
    lines.extend(_format_production_plan(report.get("production_plan", {})))

    lines.extend(["", SECTION_LINE, "", "⚠ PROBLEMI APERTI", ""])
    lines.extend(_format_problemi(report.get("problemi", {}).get("rows", [])))

    lines.extend(["", SECTION_LINE, "", "📊 STOCK", ""])
    lines.extend(_format_stock(report.get("stock", {}).get("rows", [])))

    lines.extend(["", SECTION_LINE, "", "✅ AZIONI OPERATIVE", ""])
    lines.extend(_format_azioni(report.get("azioni_operative", [])))

    schema_status = _schema_status(report)
    lines.extend(
        [
            "",
            SECTION_LINE,
            "",
            "TPO v1.0 — Morning Brief",
            f"Fonte documenti: {report.get('document_source', 'github')}",
            f"Google Sheets: {report.get('google_sheets', 'OK')}",
            f"Schema: {schema_status}",
        ]
    )

    return "\n".join(lines)


def print_report(report: dict[str, Any]) -> None:
    print(format_human_brief(report))


def _format_consegne(rows: list[dict[str, Any]]) -> list[str]:
    valid_rows = [row for row in rows if _has_content(row)]
    if not valid_rows:
        return ["Nessuna consegna attiva."]

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in valid_rows:
        key = (str(row.get("PROSSIMA_CONSEGNA", "DA CONFERMARE")), str(row.get("CLIENTE", "")))
        grouped.setdefault(key, []).append(row)

    lines: list[str] = []
    for (date, client), group in sorted(grouped.items(), key=lambda item: item[0]):
        status = _first_value(group, "STATO") or "DA CONFERMARE"
        lines.append(f"• {date} — {client}")
        lines.append(f"  Stato: {status}")
        for row in group:
            product = row.get("PRODOTTO", "Prodotto non specificato")
            quantity = row.get("QUANTITÀ") or row.get("QUANTITA") or ""
            unit = row.get("UNITÀ") or row.get("UNITA") or ""
            lines.append(f"  - {product}: {quantity} {unit}".rstrip())
            if row.get("NOTE"):
                lines.append(f"    Note: {row['NOTE']}")
    return lines


def _format_lotti(rows: list[dict[str, Any]]) -> list[str]:
    buckets = {
        "germinazione": [],
        "luce": [],
        "raccolto / chiuso / fine ciclo": [],
        "altro": [],
    }
    for row in rows:
        if not _has_content(row):
            continue
        fase = str(row.get("FASE", "")).lower()
        stato = str(row.get("STATO", "")).lower()
        if "germinazione" in fase:
            buckets["germinazione"].append(row)
        elif "luce" in fase:
            buckets["luce"].append(row)
        elif any(word in f"{fase} {stato}" for word in ("raccolto", "chiuso", "fine ciclo")):
            buckets["raccolto / chiuso / fine ciclo"].append(row)
        else:
            buckets["altro"].append(row)

    lines: list[str] = []
    for title, group in buckets.items():
        if not group:
            continue
        lines.append(title.upper())
        for row in group:
            lot_id = row.get("CALENDARIO_PROD") or row.get("ID_LOTTO") or "ID non specificato"
            lines.append(f"• {lot_id} — {row.get('VARIETA', 'varietà non specificata')}")
            lines.append(f"  Set: {row.get('SET', '')}")
            lines.append(f"  Fase: {row.get('FASE', '')} | Stato: {row.get('STATO', '')}")
            lines.append(f"  Semina: {row.get('DATA_SEMINA', '')}")
            lines.append(f"  Passaggio: {row.get('DATA_PASSAGGIO', '')}")
            lines.append(f"  Raccolta prevista: {row.get('DATA_RACCOLTA', '')}")
            if row.get("NOTE"):
                lines.append(f"  Note: {row['NOTE']}")
    return lines or ["Nessun lotto da mostrare."]


def _format_problemi(rows: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    closed = {"RISOLTO", "CHIUSO", "CLOSED", "DONE"}
    for row in rows:
        if not _has_content(row):
            continue
        if str(row.get("STATO", "")).upper() in closed:
            continue
        lines.append(f"• {row.get('GRAVITÀ') or row.get('GRAVITA') or 'DA VALUTARE'} — {row.get('AREA', '')}")
        lines.append(f"  Problema: {row.get('PROBLEMA', '')}")
        lines.append(f"  Azione richiesta: {row.get('AZIONE_RICHIESTA', '')}")
        if row.get("NOTE"):
            lines.append(f"  Note: {row['NOTE']}")
    return lines or ["Nessun problema aperto."]


def _format_stock(rows: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for row in rows:
        if not _has_content(row):
            continue
        disponibile = _decimal(row.get("DISPONIBILE"))
        prenotato = _decimal(row.get("PRENOTATO"))
        vendibile = _decimal(row.get("VENDIBILE"))
        marker = "🔴" if disponibile < prenotato else "🟡" if vendibile <= 0 else "🟢"
        variety = row.get("VARIETÀ") or row.get("VARIETA") or "Varietà non specificata"
        lines.append(
            f"{marker} {variety}: disponibile {_fmt_number(disponibile)}, "
            f"prenotato {_fmt_number(prenotato)}, vendibile {_fmt_number(vendibile)}"
        )
    return lines or ["Nessuno stock da mostrare."]


def _format_azioni(actions: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for action in actions:
        lines.append(
            f"• {action.get('priority', 'DA VALUTARE')} "
            f"[{action.get('source', 'N/D')}] {action.get('action', '')}"
        )
    return lines or ["Nessuna azione operativa generata."]


def _format_production_plan(plan: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    lines.append("💧 IDRATAZIONI")
    hydrations = plan.get("idratazioni_da_fare", [])
    if hydrations:
        for item in hydrations:
            lines.append(f"• {_title(item.get('varieta', 'Varietà non specificata'))}")
            lines.append(f"  Set da produrre: {_fmt_number(_decimal(item.get('set_da_produrre')))}")
            lines.append(f"  Grammi: {_fmt_number(_decimal(item.get('grammi_da_idratare')))} g")
            lines.append(f"  Motivo: {item.get('motivo', '')}")
    else:
        lines.append("Nessuna idratazione proposta.")

    lines.extend(["", "🌱 SEMINE"])
    sowings = plan.get("semine_da_fare", [])
    if sowings:
        for item in sowings:
            lines.append(f"• {_title(item.get('varieta', 'Varietà non specificata'))}")
            lines.append(f"  {item.get('azione', 'Semina diretta oggi')}")
            lines.append(f"  Set: {_fmt_number(_decimal(item.get('set_da_produrre')))}")
            if _decimal(item.get("grammi_da_idratare")) > 0:
                lines.append(f"  Grammi: {_fmt_number(_decimal(item.get('grammi_da_idratare')))} g")
    else:
        lines.append("Nessuna semina proposta.")

    lines.extend(["", "💡 PASSAGGI A LUCE"])
    light_moves = plan.get("passaggi_luce_da_fare", [])
    if light_moves:
        for item in light_moves:
            lines.append(f"• {item.get('id_lotto', '')} — {item.get('varieta', '')}")
            lines.append(f"  Seminato: {_format_iso_date(item.get('seminato'))}")
            lines.append(f"  Azione: {item.get('azione', 'valutare passaggio a luce')}")
    else:
        lines.append("Nessun passaggio a luce proposto.")

    lines.extend(["", "✂️ RACCOLTI"])
    harvests = plan.get("raccolti_da_fare", [])
    if harvests:
        for item in harvests:
            lines.append(f"• {item.get('id_lotto', '')} — {item.get('varieta', '')}")
            lines.append("  Raccolta prevista oggi")
            lines.append(
                f"  Destinazione possibile: {item.get('destinazione_possibile', 'consegne attive / stock')}"
            )
    else:
        lines.append("Nessuna raccolta proposta.")

    notes = plan.get("note_operatore", [])
    if notes:
        lines.extend(["", "NOTE OPERATORE"])
        for note in notes:
            lines.append(f"• {note}")

    return lines


def _schema_status(report: dict[str, Any]) -> str:
    schema_validation = report.get("schema_validation")
    return "errori" if schema_validation else "OK"


def _decimal(value: Any) -> Decimal:
    normalized = str(value or "").strip().replace(",", ".")
    if not normalized:
        return Decimal("0")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return Decimal("0")


def _fmt_number(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(value.quantize(Decimal("1")))
    return str(value.normalize())


def _format_iso_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return text


def _has_content(row: dict[str, Any]) -> bool:
    return any(str(value).strip() for value in row.values())


def _title(value: Any) -> str:
    return str(value).replace("_", " ").title()


def _first_value(rows: list[dict[str, Any]], key: str) -> Any:
    for row in rows:
        if row.get(key):
            return row[key]
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Esegue il comando AGGIORNAMI.")
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--json", action="store_true", help="Stampa il report in formato JSON.")
    args = parser.parse_args()

    try:
        report = build_report(args.config)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            print_report(report)
    except (
        MissingDocumentError,
        RepositoryNotFoundError,
        SheetsLoaderError,
        SourceNotAvailableError,
        SourceGateError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
