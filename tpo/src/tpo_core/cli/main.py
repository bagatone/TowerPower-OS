"""Entry point temporaneo della CLI runtime."""

from __future__ import annotations

import argparse
import sys

from .scheduling import run_scheduling_command


class _UsageError(ValueError):
    pass


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="tpo", description="Tower Power Operations runtime.")
    commands = parser.add_subparsers(dest="command", required=True)
    schedule = commands.add_parser("schedule", help="Comandi dello Scheduling Engine.")
    schedule_commands = schedule.add_subparsers(dest="schedule_command", required=True)
    run = schedule_commands.add_parser("run", help="Esegue una RUN in simulazione.")
    run.add_argument("--simulate", action="store_true", required=True)
    run.add_argument("--settings", required=True)
    run.add_argument("--current-system-date", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except _UsageError as exc:
        print(f"Errore di utilizzo: {exc}", file=sys.stderr)
        return 2

    return run_scheduling_command(args, stdout=sys.stdout, stderr=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
