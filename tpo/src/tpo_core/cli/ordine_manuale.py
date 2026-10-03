"""Thin CLI adapter for Ordine Manuale (``tpo ordine registra-manuale``).

Registra un ORDINE MANUALE (vendita extra / richiesta fuori programma) di un
CLIENTE esistente. Le righe si dichiarano con ``--riga VAR-000001:1:SET``
(ripetibile). Non consegna nulla: la consegna si registra con ``delivery fulfil``
usando le versioni stampate qui (ORDINE_VERSION / RIGA_VERSION).
"""
from argparse import Namespace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TextIO

from ..application.ordine_manuale.errors import (
    InvalidOrdineManualeCommandError,
    OrdineManualeError,
    OrdineManualeReconciliationRequiredError,
)
from ..application.ordine_manuale.models import (
    OrdineManualeAuthority, RegistraOrdineManuale, RigaOrdineManuale,
)
from ..bootstrap import build_ordine_manuale_service
from ..domain.identifiers import ActorId, ClienteId, VarietaId
from ..domain.quantities import UnitOfMeasure
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def _riga(raw: str) -> RigaOrdineManuale:
    parts = raw.split(":")
    if len(parts) != 3:
        raise InvalidOrdineManualeCommandError("--riga deve essere VAR-000001:QUANTITA:UNITA.")
    try:
        quantita = Decimal(parts[1])
    except InvalidOperation as exc:
        raise InvalidOrdineManualeCommandError("--riga: quantita non decimale.") from exc
    try:
        unita = UnitOfMeasure(parts[2])
    except ValueError as exc:
        raise InvalidOrdineManualeCommandError("--riga: unita deve essere GRAM o SET.") from exc
    return RigaOrdineManuale(VarietaId(parts[0]), quantita, unita)


def _data(name: str, raw: str | None) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise InvalidOrdineManualeCommandError(f"{name} deve essere una data ISO 8601.") from exc


def run_ordine_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.ordine_command != "registra-manuale":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        data_ordine = _data("--data-ordine", args.data_ordine)
        command = RegistraOrdineManuale(
            client_id=ClienteId(args.client),
            data_ordine=data_ordine,
            data_consegna_prevista=_data("--data-consegna-prevista", args.data_consegna_prevista),
            righe=tuple(_riga(raw) for raw in args.riga),
            authority=OrdineManualeAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
        )
        service = build_ordine_manuale_service(PostgreSQLSettings.from_environment())
        result = service.registra(command)
    except OrdineManualeReconciliationRequiredError as exc:
        print(f"ORDINE_MANUALE_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, OrdineManualeError) as exc:
        code = getattr(exc, "code", "ORDINE_MANUALE_INPUT_INVALID")
        print(f"ORDINE_MANUALE_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidOrdineManualeCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print(f"ORDINE_ID={result.ordine_id.value}", file=stdout)
    print(f"CLIENTE_ID={result.client_id.value}", file=stdout)
    print(f"STATO={result.stato}", file=stdout)
    print(f"ORDINE_VERSION={result.version}", file=stdout)
    for riga in result.righe:
        print(
            f"RIGA={riga.riga_id.value} POS={riga.posizione} VARIETA={riga.varieta_id.value} "
            f"QUANTITA={riga.quantita} UOM={riga.unita_misura.value} VERSION=0",
            file=stdout,
        )
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
