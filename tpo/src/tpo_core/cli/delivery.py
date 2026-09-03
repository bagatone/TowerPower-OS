"""Thin CLI adapter for Delivery Fulfilment V1 (CONSEGNA + STOCK, ordinary lines).

Scope V1: espone esclusivamente righe ordinarie (nessuna rettifica/correction_of).
Le rettifiche commerciali restano disponibili nel boundary application/infrastructure
ma non sono ancora esposte da questo comando.

Idempotenza: ConsegnaId e MovimentoId sono identità permanenti allocate una sola
volta (compare-and-set su tpo.id_sequences). Se una pubblicazione precedente
termina con esito incerto (RECONCILIATION_REQUIRED), l'operatore NON deve
rilanciare alla cieca: deve fornire esplicitamente --consegna-id e i
"movement_id" già allocati nel file --lines (vedi campo opzionale per riga) per
riutilizzare le stesse identità già commissionate, oppure verificare lo stato
reale prima di allocarne di nuove.
"""

from __future__ import annotations

import json
from argparse import Namespace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TextIO

from ..application.delivery_fulfilment.errors import (
    DeliveryCommitOutcomeUncertain,
    DeliveryFulfilmentError,
    InvalidDeliveryCommandError,
)
from ..application.delivery_fulfilment.models import (
    DeliveryFulfilmentCommand,
    DeliveryFulfilmentLine,
)
from ..application.identity.errors import IdentityAllocationError
from ..bootstrap import build_delivery_fulfilment_service, build_delivery_id_allocator
from ..domain.identifiers import ActorId, ClienteId, ConsegnaId, MovimentoId, OrdineId
from ..domain.quantities import UnitOfMeasure
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_delivery_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.delivery_command != "fulfil":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        raw_lines = json.loads(Path(args.lines_file).read_text())
        if not isinstance(raw_lines, list) or not raw_lines:
            raise InvalidDeliveryCommandError("--lines-file deve contenere una lista JSON non vuota.")

        settings = PostgreSQLSettings.from_environment()
        allocator = build_delivery_id_allocator(settings)

        delivery_id = (
            ConsegnaId(args.consegna_id)
            if args.consegna_id
            else allocator.allocate(ConsegnaId).identifier
        )

        lines: list[DeliveryFulfilmentLine] = []
        for raw_line in raw_lines:
            if not isinstance(raw_line, dict):
                raise InvalidDeliveryCommandError("Ogni riga di --lines-file deve essere un oggetto JSON.")
            movement_id = (
                MovimentoId(raw_line["movement_id"])
                if raw_line.get("movement_id")
                else allocator.allocate(MovimentoId).identifier
            )
            lines.append(DeliveryFulfilmentLine(
                order_id=OrdineId(raw_line["order_id"]),
                order_line_id=raw_line["order_line_id"],
                quantity=_decimal(raw_line["quantity"]),
                unit=UnitOfMeasure(raw_line["unit"]),
                expected_order_version=raw_line["expected_order_version"],
                expected_order_line_version=raw_line["expected_order_line_version"],
                movement_id=movement_id,
            ))

        command = DeliveryFulfilmentCommand(
            delivery_id=delivery_id,
            client_id=ClienteId(args.client),
            planned_date=_date(args.planned_date),
            effective_at=_datetime(args.effective_at),
            lines=tuple(lines),
            actor=ActorId(args.actor),
            reason=args.reason,
            correlation_id=args.correlation_id,
            operator=args.operator,
            physical_destination=args.physical_destination,
        )
        service = build_delivery_fulfilment_service(settings)
        result = service.publish(command)
    except DeliveryCommitOutcomeUncertain as exc:
        print(f"DELIVERY_FULFILMENT_FAILED: {exc}", file=stderr)
        print(f"CONSEGNA_ID_DA_RICONCILIARE: {delivery_id.value}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (KeyError,) as exc:
        print(f"DELIVERY_FULFILMENT_FAILED: campo mancante nel file righe: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_INPUT_INVALID
    except IdentityAllocationError as exc:
        print(f"DELIVERY_FULFILMENT_FAILED: allocazione identità fallita: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_FAILED
    except (ValueError, TypeError, DeliveryFulfilmentError) as exc:
        print(f"DELIVERY_FULFILMENT_FAILED: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidDeliveryCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print("STATUS: COMMITTED", file=stdout)
    print("ENTITY: CONSEGNA", file=stdout)
    print(f"CONSEGNA_ID: {result.delivery_id.value}", file=stdout)
    print(f"RIGHE: {result.delivery_line_count}", file=stdout)
    print(f"MOVIMENTI: {result.movement_count}", file=stdout)
    for order_id, state in result.order_states:
        print(f"ORDINE: {order_id.value} -> {state}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED


def _decimal(value: Any) -> Decimal:
    if isinstance(value, (float, bool)):
        raise InvalidDeliveryCommandError("quantity non accetta float o booleani nel JSON.")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidDeliveryCommandError("quantity non è un decimale valido.") from exc


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InvalidDeliveryCommandError("--planned-date deve essere una data ISO 8601.") from exc


def _datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidDeliveryCommandError("--effective-at deve essere un datetime ISO 8601.") from exc
