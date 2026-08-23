"""Thin CLI adapter for governed operational-data onboarding."""

from __future__ import annotations

from argparse import Namespace
from datetime import date, datetime, time
from decimal import Decimal
from typing import TextIO

from ..application.onboarding.errors import OperationalDataOnboardingError
from ..application.onboarding.models import (
    CommissionCustomer, CommissionSupplyProgram, CommissionVariety,
    CorrectNeverEffectiveSupplyProgramVersion, OnboardingAuthority,
)
from ..bootstrap import build_operational_data_onboarding_service
from ..domain.entities.programma_fornitura import (
    ConfigurazioneTemporale, ProgrammaFornitura, RigaProgrammaFornitura, TipoRicorrenza,
)
from ..domain.entities.varieta import Varieta
from ..domain.identifiers import ActorId, ClienteId, ProgrammaFornituraId, VarietaId
from ..domain.quantities import Quantity, UnitOfMeasure
from ..domain.states import ProgrammaFornituraState, VarietaState
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_onboarding_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        authority = OnboardingAuthority(ActorId(args.actor), args.reason, args.correlation_id)
        if args.onboarding_command == "customer":
            command = CommissionCustomer(ClienteId(args.customer_id), args.denomination, authority)
            method = "commission_customer"
        elif args.onboarding_command == "variety":
            command = CommissionVariety(
                Varieta(VarietaId(args.variety_id), args.denomination, VarietaState(args.state)), authority,
            )
            method = "commission_variety"
        else:
            lines = tuple(_line(value) for value in args.line)
            program = ProgrammaFornitura(
                ProgrammaFornituraId(args.program_id), ClienteId(args.customer_id), lines,
                date.fromisoformat(args.start_date), ProgrammaFornituraState(args.state),
                args.operational_window_days,
                date.fromisoformat(args.end_date) if args.end_date else None,
                time.fromisoformat(args.generation_time),
            )
            if args.onboarding_command == "supply-program":
                command = CommissionSupplyProgram(
                    program, args.version, datetime.fromisoformat(args.valid_from), authority,
                )
                method = "commission_supply_program"
            else:
                command = CorrectNeverEffectiveSupplyProgramVersion(
                    program, args.expected_current_version,
                    datetime.fromisoformat(args.valid_from), authority,
                )
                method = "correct_never_effective_supply_program_version"
        service = build_operational_data_onboarding_service(PostgreSQLSettings.from_environment())
        result = getattr(service, method)(command)
    except (ValueError, TypeError, OperationalDataOnboardingError) as exc:
        print(f"ONBOARDING_FAILED: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_FAILED
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"STATUS: {'INSERTED' if result.inserted else 'COMPATIBLE_REPLAY'}", file=stdout)
    print(f"ENTITY: {result.entity_type}", file=stdout)
    print(f"PUBLIC_ID: {result.public_id}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED


def _line(value: str) -> RigaProgrammaFornitura:
    parts = value.split(",")
    if len(parts) != 6:
        raise ValueError("--line richiede VARIETY_ID,QUANTITY,UOM,RECURRENCE,INTERVAL,DAYS.")
    variety, quantity, uom, recurrence, interval, days = parts
    temporal = ConfigurazioneTemporale(
        TipoRicorrenza(recurrence), int(interval) if interval else None,
        tuple(int(day) for day in days.split("+") if day),
    )
    return RigaProgrammaFornitura(
        VarietaId(variety), Quantity(Decimal(quantity), UnitOfMeasure(uom)), temporal,
    )
