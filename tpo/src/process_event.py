from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .event_engine import EventEngine, OperationalEvent, WEEKDAY_LABELS
from .sheets_writer import SheetsWriter


def main() -> None:
    parser = argparse.ArgumentParser(description="Processa eventi TPOL con Event Engine MVP.")
    parser.add_argument("--input", required=True, help="Percorso del file evento JSON.")
    parser.add_argument("--config", default="config/settings.yaml")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.apply:
        print("Apply non supportato nell'Event Engine MVP. Usare --dry-run.", file=sys.stderr)
        raise SystemExit(1)

    try:
        event = OperationalEvent.from_json_file(args.input)
        engine = EventEngine.from_default_sources(config_path=args.config)
        result = engine.process(event)
        if result.write_plan and not result.errors:
            write_plan_errors = validate_write_plan_offline(result.write_plan)
            for error in write_plan_errors:
                result.block(f"WritePlan non valido: {error}")
        print(format_event_result(result))
        if result.errors:
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None


def validate_write_plan_offline(write_plan) -> list[str]:
    writer = SheetsWriter(allow_offline=True)
    result, _ = writer._preflight(write_plan)
    return result.errors


def format_event_result(result) -> str:
    payload = result.event.payload
    lines = [
        "TOWERPOWER OS - EVENT ENGINE MVP",
        "",
        f"Evento: {result.event.event_type}",
        f"Event ID: {result.event.event_id}",
        f"Stato: {result.status.value}",
    ]
    if result.event.event_type == "SEMINA":
        lines.extend(
            [
                "",
                f"Varietà: {payload.get('varieta', '')}",
                f"Set: {payload.get('set', '')}",
                f"ID Lotto: {payload.get('id_lotto', '')}",
            ]
        )
    if result.event.event_type == "NUOVO_ORDINE_RICORRENTE":
        lines.extend(_format_recurring_order_result(result))
    if result.consumi:
        lines.extend(["", "Consumi:"])
        for item in result.consumi:
            lines.append(
                f"- {item['risorsa']}: {item['quantita']} {item['unita']}"
            )
    if result.write_plan:
        lines.extend(["", "WritePlan:"])
        for operation in result.write_plan.operations:
            lines.append(f"- {operation.sheet_name}: {len(operation.rows)} righe")
    if result.errors:
        lines.extend(["", "Errori:"])
        lines.extend(f"- {error}" for error in result.errors)
    lines.extend(["", "Nessuna scrittura eseguita."])
    return "\n".join(lines)


def _format_recurring_order_result(result) -> list[str]:
    payload = result.event.payload
    lines = [
        f"Cliente: {payload.get('cliente', '')}",
        "",
        "Ordine:",
    ]
    for product in payload.get("prodotti", []):
        lines.append(
            f"- {product.get('varieta', '')}: {product.get('quantita', '')} {product.get('unita', '')}"
        )

    delivery = str(payload.get("prima_consegna", ""))
    weekday = ""
    try:
        parsed = datetime.strptime(delivery, "%Y-%m-%d").date()
        weekday = WEEKDAY_LABELS[parsed.weekday()]
    except ValueError:
        weekday = str(payload.get("giorno_consegna", ""))

    lines.extend(
        [
            "",
            "Frequenza:",
            f"- ogni {payload.get('frequenza_giorni', '')} giorni",
            f"- {str(payload.get('giorno_consegna', '')).lower()}",
            "",
            "Prima consegna:",
            f"- {delivery} — {weekday}",
        ]
    )

    if result.calendar_preview:
        lines.extend(["", "Pianificazione:"])
        for item in result.calendar_preview:
            lines.append(
                f"- {item['varieta']}: semina {item['data_semina']}, "
                f"raccolta {item['data_raccolta']}"
            )

    if result.resource_commitment_preview:
        lines.extend(["", "Risorse impegnate:"])
        for item in result.resource_commitment_preview:
            availability = f", disponibile {item.get('disponibile')}" if item.get("disponibile") else ""
            lines.append(
                f"- {item['risorsa']}: {item['quantita']} {item['unita']}{availability}"
            )

    if result.stock_delta_preview:
        lines.extend(["", "Stock delta preview:"])
        for item in result.stock_delta_preview:
            lines.append(
                f"- {item['varieta']}: PRENOTATO +{item['delta_prenotato']} {item['unita']}"
            )

    if result.provenance:
        lines.extend(["", "Provenance:"])
        for item in result.provenance:
            lines.append(f"- {item.source_type}:{item.source_name} letto={item.read_successfully}")

    if result.warnings:
        lines.extend(["", "Warning:"])
        lines.extend(f"- {warning}" for warning in result.warnings)

    if result.blocking_errors:
        lines.extend(["", "Blocking errors:"])
        lines.extend(f"- {error}" for error in result.blocking_errors)

    return lines


if __name__ == "__main__":
    main()
