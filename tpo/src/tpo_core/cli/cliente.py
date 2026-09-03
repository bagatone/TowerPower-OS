"""Thin CLI adapter per la Configuration mutabile di fatturazione CLIENTE."""

from __future__ import annotations

from argparse import Namespace
from typing import TextIO

from ..bootstrap import build_cliente_fatturazione_writer
from ..infrastructure.postgresql.fatturazione_configuration import (
    FatturazioneConfigurationError,
)
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode

_VALID_MODALITA = ("A_CONSEGNA", "PERIODICA_MENSILE")


def run_cliente_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.cliente_command != "fatturazione":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        if args.modalita_fatturazione not in _VALID_MODALITA:
            raise ValueError("--modalita-fatturazione deve essere A_CONSEGNA o PERIODICA_MENSILE.")
        if args.termini_pagamento_giorni <= 0:
            raise ValueError("--termini-pagamento-giorni deve essere positivo.")
        writer = build_cliente_fatturazione_writer(PostgreSQLSettings.from_environment())
        writer.set_fatturazione(
            cliente_public_id=args.client, modalita_fatturazione=args.modalita_fatturazione,
            termini_pagamento_giorni=args.termini_pagamento_giorni, actor=args.actor,
        )
    except (ValueError, TypeError, FatturazioneConfigurationError) as exc:
        print(f"CLIENTE_FATTURAZIONE_SET_FAILED: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_INPUT_INVALID
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print("STATUS: COMMITTED", file=stdout)
    print("ENTITY: CLIENTE", file=stdout)
    print(f"CLIENTE: {args.client}", file=stdout)
    print(f"MODALITA_FATTURAZIONE: {args.modalita_fatturazione}", file=stdout)
    print(f"TERMINI_PAGAMENTO_GIORNI: {args.termini_pagamento_giorni}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
