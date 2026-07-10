from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .event_engine import EventEngine, OperationalEvent


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
        print(format_event_result(result))
        if result.errors:
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None


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


if __name__ == "__main__":
    main()
