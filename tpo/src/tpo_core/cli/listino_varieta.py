"""Thin CLI adapter per la Configuration governata LISTINO_VARIETA.

Autorità: docs/architecture/LISTINO_VARIETA_GOVERNANCE_FREEZE.md.
"""

from __future__ import annotations

from argparse import Namespace
from decimal import Decimal, InvalidOperation
from typing import TextIO

from ..application.listino_varieta.errors import (
    InvalidListinoVarietaCommandError, ListinoVarietaVarietaNotFoundError,
)
from ..application.listino_varieta.models import (
    ImpostaPrezzoListinoVarieta, ListinoVarietaAuthority,
)
from ..bootstrap import build_listino_varieta_writer
from ..domain.identifiers import ActorId, InvalidIdentifierError, VarietaId
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_listino_varieta_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.listino_varieta_command != "set":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        command = ImpostaPrezzoListinoVarieta(
            VarietaId(args.varieta),
            _decimal("--prezzo-unitario", args.prezzo_unitario),
            _decimal("--aliquota-igic", args.aliquota_igic),
            ListinoVarietaAuthority(
                ActorId(args.actor), args.reason, args.correlation_id,
            ),
        )
        writer = build_listino_varieta_writer(PostgreSQLSettings.from_environment())
        result = writer.imposta_prezzo(command)
    except (ValueError, TypeError, InvalidIdentifierError, InvalidListinoVarietaCommandError,
            ListinoVarietaVarietaNotFoundError) as exc:
        print(f"LISTINO_VARIETA_SET_FAILED: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_INPUT_INVALID
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print("STATUS: COMMITTED", file=stdout)
    print("ENTITY: LISTINO_VARIETA", file=stdout)
    print(f"VARIETA: {result.varieta_public_id}", file=stdout)
    print(f"PREZZO_UNITARIO: {result.prezzo_unitario}", file=stdout)
    print(f"ALIQUOTA_IGIC: {result.aliquota_igic}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED


def _decimal(name: str, value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} deve essere un decimale valido.") from exc
