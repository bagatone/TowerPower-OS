"""Thin CLI adapter per la Configuration mutabile LISTINO_VARIETA."""

from __future__ import annotations

from argparse import Namespace
from decimal import Decimal, InvalidOperation
from typing import TextIO

from ..bootstrap import build_listino_varieta_writer
from ..infrastructure.postgresql.fatturazione_configuration import (
    FatturazioneConfigurationError,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_listino_varieta_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.listino_varieta_command != "set":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        prezzo_unitario = _decimal("--prezzo-unitario", args.prezzo_unitario)
        aliquota_igic = _decimal("--aliquota-igic", args.aliquota_igic)
        writer = build_listino_varieta_writer(PostgreSQLSettings.from_environment())
        writer.set_prezzo(
            varieta_public_id=args.varieta, prezzo_unitario=prezzo_unitario,
            aliquota_igic=aliquota_igic, actor=args.actor,
        )
    except (ValueError, TypeError, FatturazioneConfigurationError) as exc:
        print(f"LISTINO_VARIETA_SET_FAILED: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_INPUT_INVALID
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print("STATUS: COMMITTED", file=stdout)
    print("ENTITY: LISTINO_VARIETA", file=stdout)
    print(f"VARIETA: {args.varieta}", file=stdout)
    print(f"PREZZO_UNITARIO: {prezzo_unitario}", file=stdout)
    print(f"ALIQUOTA_IGIC: {aliquota_igic}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED


def _decimal(name: str, value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} deve essere un decimale valido.") from exc
