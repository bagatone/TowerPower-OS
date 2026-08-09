"""Adapter CLI sottile per l'Operational Scheduling Entry Point."""

from __future__ import annotations

import re
from argparse import Namespace
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Callable, TextIO

from ..application.operational_entrypoint import (
    OperationalEntryPointResult,
    OperationalSchedulingIntent,
    RecognizedOperationalIdentity,
)
from ..bootstrap import (
    OperationalRuntimeUnavailableError,
    build_operational_application,
)
from ..bootstrap.settings import InvalidSettingsError
from ..domain.time_reference import CurrentSystemDate, OFFICIAL_TIMEZONE
from .exit_codes import OperationalExitCode


@dataclass(frozen=True)
class OperationalCliDependencies:
    application_factory: Callable[..., Any] = build_operational_application


def run_operational_scheduling_command(
    args: Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
    dependencies: OperationalCliDependencies | None = None,
) -> int:
    dependencies = dependencies or OperationalCliDependencies()

    if args.confirm is not True:
        return _input_invalid("--confirm è obbligatorio.", stderr)

    try:
        business_date = _parse_business_reference(
            args.business_date, args.business_time
        )
        identity = RecognizedOperationalIdentity(args.identity)
        intent = OperationalSchedulingIntent(
            business_date=business_date,
            operational_identity=identity,
        )
    except (TypeError, ValueError) as exc:
        return _input_invalid(str(exc), stderr)

    try:
        container = dependencies.application_factory(args.settings)
    except InvalidSettingsError as exc:
        return _input_invalid(str(exc), stderr)
    except OperationalRuntimeUnavailableError:
        print("OPERATION_RUNTIME_UNAVAILABLE", file=stderr)
        return OperationalExitCode.OPERATION_RUNTIME_UNAVAILABLE

    entry_point = container.operational_scheduling_entry_point
    if entry_point is None:
        print("OPERATION_RUNTIME_UNAVAILABLE", file=stderr)
        return OperationalExitCode.OPERATION_RUNTIME_UNAVAILABLE

    try:
        result = entry_point.execute(intent)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(_format_result(result), file=stdout)
    return _exit_for(result.status)


def _parse_business_reference(
    date_value: str, time_value: str
) -> CurrentSystemDate:
    if (
        not isinstance(date_value, str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value) is None
    ):
        raise ValueError("--business-date deve usare il formato YYYY-MM-DD.")
    if (
        not isinstance(time_value, str)
        or re.fullmatch(r"\d{2}:\d{2}", time_value) is None
    ):
        raise ValueError("--business-time deve usare il formato HH:MM.")
    try:
        parsed_date = date.fromisoformat(date_value)
    except ValueError as exc:
        raise ValueError("--business-date non è una data valida.") from exc
    try:
        parsed_time = time.fromisoformat(time_value)
    except ValueError as exc:
        raise ValueError("--business-time non è un orario valido.") from exc
    return CurrentSystemDate(
        datetime.combine(parsed_date, parsed_time, OFFICIAL_TIMEZONE)
    )


def _input_invalid(message: str, stderr: TextIO) -> OperationalExitCode:
    print(f"OPERATION_INPUT_INVALID: {message}", file=stderr)
    return OperationalExitCode.OPERATION_INPUT_INVALID


def _exit_for(status: Any) -> OperationalExitCode:
    return {
        "COMMITTED": OperationalExitCode.OPERATION_COMMITTED,
        "FAILED": OperationalExitCode.OPERATION_FAILED,
        "RECONCILIATION_REQUIRED": (
            OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
        ),
    }[status.value]


def _format_result(result: OperationalEntryPointResult) -> str:
    lines = [f"STATUS: {result.status.value}", f"RUN_ID: {result.run_id.value}"]
    if result.status.value == "FAILED":
        lines.append("ERRORS:")
        lines.extend(f"- {error}" for error in result.errors)
        if not result.errors:
            lines.append("- nessuno")
        if result.completed_run is not None:
            lines.append(f"RUN_STATE: {result.completed_run.state.value}")
    lines.append("WARNINGS:")
    lines.extend(f"- {warning}" for warning in result.warnings)
    if not result.warnings:
        lines.append("- nessuno")
    if result.status.value == "RECONCILIATION_REQUIRED":
        context = result.reconciliation_context
        if context is None:
            raise ValueError("RECONCILIATION_REQUIRED privo del contesto pubblico.")
        lines.extend(
            (
                "RECONCILIATION:",
                f"  RUN_ID: {context.run_id.value}",
                f"  REQUESTED_AT: {context.requested_at.datetime.isoformat()}",
                f"  CORRELATION_ID: {context.correlation_id}",
                f"  EXPECTED_RECORD_COUNT: {context.expected_record_count}",
                f"  EXPECTED_LOGICAL_ROW_COUNT: {context.expected_logical_row_count}",
                "  IDEMPOTENCY_KEYS:",
            )
        )
        lines.extend(f"  - {key}" for key in context.idempotency_keys)
    return "\n".join(lines)
