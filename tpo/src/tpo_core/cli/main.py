"""Entry point temporaneo della CLI runtime."""

from __future__ import annotations

import argparse
import sys

from ..domain.states import VarietaState
from .scheduling import run_scheduling_command
from .preflight import run_preflight_command
from .operational import run_operational_scheduling_command
from .production_planning import run_production_planning_command
from .onboarding import run_onboarding_command


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
    preflight = schedule_commands.add_parser(
        "preflight", help="Verifica read-only della pipeline Google Sheets."
    )
    preflight.add_argument("--settings", required=True)
    preflight.add_argument("--current-system-date", required=True)
    preflight.add_argument("--run-id", required=True)
    preflight.add_argument("--json", action="store_true", dest="json_output")
    execute = schedule_commands.add_parser(
        "execute", help="Esegue lo Scheduling operativo autorevole."
    )
    execute.add_argument("--settings", required=True)
    execute.add_argument("--business-date", required=True)
    execute.add_argument("--business-time", required=True)
    execute.add_argument("--identity", required=True)
    execute.add_argument("--confirm", action="store_true", required=True)
    planning = commands.add_parser(
        "production-planning", help="Comandi Production Planning PostgreSQL."
    )
    planning_commands = planning.add_subparsers(
        dest="production_planning_command", required=True,
    )
    for name in ("initial", "replan"):
        command = planning_commands.add_parser(
            name, help=f"Esegue Production Planning {name}."
        )
        command.add_argument("--business-at", required=True)
        command.add_argument("--policy-set-code", required=True)
        command.add_argument("--policy-version", required=True, type=int)
        command.add_argument("--actor", required=True)
        command.add_argument("--reason", required=True)
        command.add_argument("--correlation-id", required=True)
        if name == "replan":
            command.add_argument("--previous-revision-public-id", required=True)
            command.add_argument("--order-line-public-id", required=True)
            command.add_argument("--replanning-reason-code", required=True)
    onboarding = commands.add_parser("onboarding", help="Onboarding dati operativi autorevoli.")
    onboarding_commands = onboarding.add_subparsers(dest="onboarding_command", required=True)
    customer = onboarding_commands.add_parser("customer")
    customer.add_argument("--customer-id", required=True)
    customer.add_argument("--denomination", required=True)
    variety = onboarding_commands.add_parser("variety")
    variety.add_argument("--variety-id", required=True)
    variety.add_argument("--denomination", required=True)
    variety.add_argument("--state", required=True, choices=[item.value for item in VarietaState])
    program = onboarding_commands.add_parser("supply-program")
    correction = onboarding_commands.add_parser("correct-never-effective-supply-program")
    program.add_argument("--program-id", required=True)
    program.add_argument("--customer-id", required=True)
    program.add_argument("--version", required=True, type=int)
    program.add_argument("--state", required=True, choices=["ATTIVO", "SOSPESO", "TERMINATO"])
    program.add_argument("--start-date", required=True)
    program.add_argument("--end-date")
    program.add_argument("--generation-time", required=True)
    program.add_argument("--operational-window-days", required=True, type=int)
    program.add_argument("--valid-from", required=True)
    program.add_argument("--line", required=True, action="append")
    correction.add_argument("--program-id", required=True)
    correction.add_argument("--customer-id", required=True)
    correction.add_argument("--expected-current-version", required=True, type=int)
    correction.add_argument("--state", required=True, choices=["ATTIVO", "SOSPESO", "TERMINATO"])
    correction.add_argument("--start-date", required=True)
    correction.add_argument("--end-date")
    correction.add_argument("--generation-time", required=True)
    correction.add_argument("--operational-window-days", required=True, type=int)
    correction.add_argument("--valid-from", required=True)
    correction.add_argument("--line", required=True, action="append")
    for command in (customer, variety, program, correction):
        command.add_argument("--actor", required=True)
        command.add_argument("--reason", required=True)
        command.add_argument("--correlation-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except _UsageError as exc:
        print(f"Errore di utilizzo: {exc}", file=sys.stderr)
        return 2

    if args.command == "production-planning":
        return run_production_planning_command(
            args, stdout=sys.stdout, stderr=sys.stderr,
        )
    if args.command == "onboarding":
        return run_onboarding_command(args, stdout=sys.stdout, stderr=sys.stderr)
    if args.schedule_command == "preflight":
        return run_preflight_command(args, stdout=sys.stdout, stderr=sys.stderr)
    if args.schedule_command == "execute":
        return run_operational_scheduling_command(
            args, stdout=sys.stdout, stderr=sys.stderr
        )
    return run_scheduling_command(args, stdout=sys.stdout, stderr=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
