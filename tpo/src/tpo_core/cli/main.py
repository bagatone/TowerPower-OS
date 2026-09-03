"""Entry point temporaneo della CLI runtime."""

from __future__ import annotations

import argparse
import sys

from ..domain.states import SeminaFinalOutcome, SeminaState, VarietaState
from .scheduling import run_scheduling_command
from .preflight import run_preflight_command
from .operational import run_operational_scheduling_command
from .production_planning import run_production_planning_command
from .raccolta import run_raccolta_command
from .onboarding import run_onboarding_command
from .seed_lot import run_seed_lot_command
from .semente import run_semente_command
from .semina import run_semina_command


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
    variety.add_argument("--traceability-code")
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
    semente = commands.add_parser("semente", help="Commissioning governato SEMENTE.")
    semente_commands = semente.add_subparsers(dest="semente_command", required=True)
    commission_semente = semente_commands.add_parser("commission")
    commission_semente.add_argument("--fornitore", required=True)
    commission_semente.add_argument("--referenza-commerciale", required=True)
    commission_semente.add_argument("--marca")
    commission_semente.add_argument("--formato")
    commission_semente.add_argument("--trattamento")
    commission_semente.add_argument("--certificazioni")
    commission_semente.add_argument("--actor", required=True)
    commission_semente.add_argument("--reason", required=True)
    commission_semente.add_argument("--correlation-id", required=True)
    commission_semente.add_argument("--idempotency-key", required=True)
    commission_semente.add_argument("--confirm", action="store_true", required=True)
    seed_lot = commands.add_parser("seed-lot", help="Commissioning governato LOTTO_SEME.")
    seed_lot_commands = seed_lot.add_subparsers(dest="seed_lot_command", required=True)
    commission_seed_lot = seed_lot_commands.add_parser("commission")
    commission_seed_lot.add_argument("--seed-supplier", required=True)
    commission_seed_lot.add_argument("--seed-commercial-reference", required=True)
    commission_seed_lot.add_argument("--manufacturer-lot-number", required=True)
    commission_seed_lot.add_argument("--received-date", required=True)
    commission_seed_lot.add_argument("--expiry-date")
    commission_seed_lot.add_argument("--initial-quantity", required=True)
    commission_seed_lot.add_argument("--unit", required=True, choices=["GRAM"])
    commission_seed_lot.add_argument("--anomaly")
    commission_seed_lot.add_argument("--provenance", required=True)
    commission_seed_lot.add_argument("--actor", required=True)
    commission_seed_lot.add_argument("--reason", required=True)
    commission_seed_lot.add_argument("--correlation-id", required=True)
    commission_seed_lot.add_argument("--idempotency-key", required=True)
    commission_seed_lot.add_argument("--confirm", action="store_true", required=True)
    semina = commands.add_parser("semina", help="Commissioning governato SEMINA.")
    semina_commands = semina.add_subparsers(dest="semina_command", required=True)
    commission_semina = semina_commands.add_parser("commission")
    commission_semina.add_argument("--seed-lot", required=True)
    commission_semina.add_argument("--expected-seed-lot-version", required=True, type=int)
    commission_semina.add_argument("--protocol-version", required=True)
    commission_semina.add_argument("--actual-seed-grams", required=True)
    commission_semina.add_argument("--physical-started-at", required=True)
    commission_semina.add_argument("--origin", required=True, choices=[
        "PIANO_PRODUZIONE", "ORDINE_CLIENTE", "RIPRISTINO_STOCK",
    ])
    commission_semina.add_argument("--planning-line")
    commission_semina.add_argument("--expected-planning-line-version", type=int)
    commission_semina.add_argument("--started-quantity-set")
    commission_semina.add_argument("--provenance", required=True)
    commission_semina.add_argument("--actor", required=True)
    commission_semina.add_argument("--reason", required=True)
    commission_semina.add_argument("--correlation-id", required=True)
    commission_semina.add_argument("--idempotency-key", required=True)
    commission_semina.add_argument("--confirm", action="store_true", required=True)
    transition_semina = semina_commands.add_parser("transition")
    transition_semina.add_argument("--semina", required=True)
    transition_semina.add_argument("--expected-semina-version", required=True, type=int)
    transition_semina.add_argument("--target-state", required=True,
                                   choices=[state.value for state in SeminaState])
    transition_semina.add_argument("--effective-at", required=True)
    transition_semina.add_argument(
        "--final-outcome", choices=[outcome.value for outcome in SeminaFinalOutcome],
    )
    transition_semina.add_argument("--provenance", required=True)
    transition_semina.add_argument("--actor", required=True)
    transition_semina.add_argument("--reason", required=True)
    transition_semina.add_argument("--correlation-id", required=True)
    transition_semina.add_argument("--idempotency-key", required=True)
    transition_semina.add_argument("--confirm", action="store_true", required=True)
    raccolta = commands.add_parser("raccolta", help="Registrazione governata RACCOLTA.")
    raccolta_commands = raccolta.add_subparsers(dest="raccolta_command", required=True)
    record_raccolta = raccolta_commands.add_parser("record")
    record_raccolta.add_argument("--semina", required=True)
    record_raccolta.add_argument("--quantity", required=True)
    record_raccolta.add_argument("--uom", required=True, choices=["SET"])
    record_raccolta.add_argument("--effective-at", required=True)
    record_raccolta.add_argument("--notes")
    record_raccolta.add_argument("--actor", required=True)
    record_raccolta.add_argument("--reason", required=True)
    record_raccolta.add_argument("--correlation-id", required=True)
    record_raccolta.add_argument("--idempotency-key", required=True)
    record_raccolta.add_argument("--confirm", action="store_true", required=True)
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
    if args.command == "semente":
        return run_semente_command(args, stdout=sys.stdout, stderr=sys.stderr)
    if args.command == "seed-lot":
        return run_seed_lot_command(args, stdout=sys.stdout, stderr=sys.stderr)
    if args.command == "semina":
        return run_semina_command(args, stdout=sys.stdout, stderr=sys.stderr)
    if args.command == "raccolta":
        return run_raccolta_command(args, stdout=sys.stdout, stderr=sys.stderr)
    if args.schedule_command == "preflight":
        return run_preflight_command(args, stdout=sys.stdout, stderr=sys.stderr)
    if args.schedule_command == "execute":
        return run_operational_scheduling_command(
            args, stdout=sys.stdout, stderr=sys.stderr
        )
    return run_scheduling_command(args, stdout=sys.stdout, stderr=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
