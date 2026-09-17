"""Thin CLI adapter for PROGRAMMA_FORNITURA Sospensione/Riattivazione V1."""
from argparse import Namespace
from datetime import date, datetime
from typing import TextIO

from ..application.programma_fornitura_sospensione.errors import (
    InvalidProgrammaFornituraSospensioneCommandError, ProgrammaFornituraReconciliationRequiredError,
    ProgrammaFornituraSospensioneError,
)
from ..application.programma_fornitura_sospensione.models import (
    ProgrammaFornituraSospensioneAuthority, RiattivaProgrammaFornitura,
    SospendiProgrammaFornitura,
)
from ..bootstrap import build_programma_fornitura_sospensione_service
from ..domain.identifiers import ActorId, ProgrammaFornituraId
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_programma_fornitura_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.programma_fornitura_command == "sospendi":
        return _run_sospendi(args, stdout=stdout, stderr=stderr)
    if args.programma_fornitura_command == "riattiva":
        return _run_riattiva(args, stdout=stdout, stderr=stderr)
    print("OPERATION_INTERNAL_ERROR", file=stderr)
    return OperationalExitCode.OPERATION_INTERNAL_ERROR


def _run_sospendi(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        command = SospendiProgrammaFornitura(
            ProgrammaFornituraId(args.programma),
            args.expected_numero_versione,
            datetime.fromisoformat(args.effective_at),
            ProgrammaFornituraSospensioneAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
            date.fromisoformat(args.data_ripresa_prevista) if args.data_ripresa_prevista else None,
        )
        result = build_programma_fornitura_sospensione_service(
            PostgreSQLSettings.from_environment()
        ).sospendi(command)
    except ProgrammaFornituraReconciliationRequiredError as exc:
        print(f"PROGRAMMA_FORNITURA_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, ProgrammaFornituraSospensioneError) as exc:
        code = getattr(exc, "code", "PROGRAMMA_FORNITURA_SOSPENSIONE_INPUT_INVALID")
        print(f"PROGRAMMA_FORNITURA_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError,
                                    InvalidProgrammaFornituraSospensioneCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"PROGRAMMA_FORNITURA_ID={result.programma_id.value}", file=stdout)
    print(f"NUMERO_VERSIONE_PRECEDENTE={result.numero_versione_precedente}", file=stdout)
    print(f"NUMERO_VERSIONE={result.numero_versione}", file=stdout)
    print(f"STATO_PRECEDENTE={result.stato_precedente}", file=stdout)
    print(f"STATO={result.stato}", file=stdout)
    print(f"DATA_RIPRESA_PREVISTA={result.data_ripresa_prevista.isoformat() if result.data_ripresa_prevista else ''}", file=stdout)
    print(f"EFFECTIVE_AT={result.effective_at.isoformat()}", file=stdout)
    print(f"RECORDED_AT={result.recorded_at.isoformat()}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED


def _run_riattiva(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        command = RiattivaProgrammaFornitura(
            ProgrammaFornituraId(args.programma),
            args.expected_numero_versione,
            datetime.fromisoformat(args.effective_at),
            ProgrammaFornituraSospensioneAuthority(
                ActorId(args.actor), args.reason, args.correlation_id, args.idempotency_key,
            ),
        )
        result = build_programma_fornitura_sospensione_service(
            PostgreSQLSettings.from_environment()
        ).riattiva(command)
    except ProgrammaFornituraReconciliationRequiredError as exc:
        print(f"PROGRAMMA_FORNITURA_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, ProgrammaFornituraSospensioneError) as exc:
        code = getattr(exc, "code", "PROGRAMMA_FORNITURA_SOSPENSIONE_INPUT_INVALID")
        print(f"PROGRAMMA_FORNITURA_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError,
                                    InvalidProgrammaFornituraSospensioneCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print(f"PROGRAMMA_FORNITURA_ID={result.programma_id.value}", file=stdout)
    print(f"NUMERO_VERSIONE_PRECEDENTE={result.numero_versione_precedente}", file=stdout)
    print(f"NUMERO_VERSIONE={result.numero_versione}", file=stdout)
    print(f"STATO_PRECEDENTE={result.stato_precedente}", file=stdout)
    print(f"STATO={result.stato}", file=stdout)
    print(f"EFFECTIVE_AT={result.effective_at.isoformat()}", file=stdout)
    print(f"RECORDED_AT={result.recorded_at.isoformat()}", file=stdout)
    print(f"OUTCOME={result.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
