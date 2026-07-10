from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .sheets_writer import SheetsWriter, WritePlan


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrive righe validate nei Google Sheets TPO.")
    parser.add_argument("--input", required=True, help="Percorso del file JSON con il piano di scrittura.")
    parser.add_argument("--config", default="config/settings.yaml")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    try:
        plan = WritePlan.from_json_file(args.input)
        writer = SheetsWriter.from_config_path(args.config, allow_offline=args.dry_run)
        result = writer.dry_run(plan) if args.dry_run else writer.apply(plan)
        print(_format_result(result))
        if result.errors:
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None


def _format_result(result) -> str:
    lines = [
        "TOWERPOWER OS - GOOGLE SHEETS WRITER",
        f"Modalità: {result.mode.upper()}",
        f"Esito: {'OK' if result.success else 'BLOCCATO'}",
        "Righe richieste:",
    ]
    for sheet_name, count in result.rows_requested.items():
        lines.append(f"- {sheet_name}: {count}")
    lines.append("Righe valide:")
    for sheet_name, count in result.rows_valid.items():
        lines.append(f"- {sheet_name}: {count}")
    if result.rows_written:
        lines.append("Righe scritte:")
        for sheet_name, count in result.rows_written.items():
            lines.append(f"- {sheet_name}: {count}")
    if result.duplicates:
        lines.append("Duplicati:")
        for sheet_name, rows in result.duplicates.items():
            lines.append(f"- {sheet_name}: {len(rows)}")
    if result.errors:
        lines.append("Errori:")
        lines.extend(f"- {error}" for error in result.errors)
    if result.log_path:
        lines.append(f"Log: {result.log_path}")
    if result.mode == "dry-run":
        lines.append("Nessuna scrittura eseguita.")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
