"""Thin CLI adapter per CONSUMO_MATERIALI_SEMINA V1."""
from argparse import Namespace
from datetime import datetime
from typing import TextIO

from ..application.consumo_materiali import (
    ConsumoMaterialiAuthority, ConsumoMaterialiError, InvalidConsumoMaterialiCommandError,
    RegistraConsumoMaterialiSemina,
)
from ..application.movimento_articolo.errors import (
    MovimentoArticoloError, MovimentoArticoloReconciliationRequiredError,
)
from ..bootstrap import build_consumo_materiali_service
from ..domain.identifiers import ActorId, ArticoloId, SeminaId
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_consumo_materiali_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.materiali_command != "consumo-semina":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        effective_at = None
        if args.effective_at:
            try:
                effective_at = datetime.fromisoformat(args.effective_at)
            except ValueError as exc:
                raise InvalidConsumoMaterialiCommandError(
                    "--effective-at deve essere una data/ora ISO 8601."
                ) from exc
        command = RegistraConsumoMaterialiSemina(
            semina_id=SeminaId(args.semina),
            set_seminati=args.set_seminati,
            pezzi_per_set=args.pezzi_per_set,
            articolo_vaschette=ArticoloId(args.articolo_vaschette) if args.articolo_vaschette else None,
            articolo_substrato=ArticoloId(args.articolo_substrato) if args.articolo_substrato else None,
            effective_at=effective_at,
            authority=ConsumoMaterialiAuthority(ActorId(args.actor), args.reason, args.correlation_id),
        )
        service = build_consumo_materiali_service(PostgreSQLSettings.from_environment())
        result = service.registra(command)
    except MovimentoArticoloReconciliationRequiredError as exc:
        print(f"CONSUMO_MATERIALI_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RECONCILIATION_REQUIRED
    except (ValueError, TypeError, ConsumoMaterialiError, MovimentoArticoloError) as exc:
        code = getattr(exc, "code", "CONSUMO_MATERIALI_INPUT_INVALID")
        print(f"CONSUMO_MATERIALI_FAILED: {code}: {exc}", file=stderr)
        return (OperationalExitCode.OPERATION_INPUT_INVALID
                if isinstance(exc, (ValueError, TypeError, InvalidConsumoMaterialiCommandError))
                else OperationalExitCode.OPERATION_FAILED)
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print(f"SEMINA_ID={result.semina_id.value}", file=stdout)
    print(f"CODICE_TRACCIABILITA={result.codice_tracciabilita}", file=stdout)
    print(f"SET={result.set_seminati}", file=stdout)
    print(f"PEZZI_PER_SET={result.pezzi_per_set}", file=stdout)
    for etichetta, r in (("VASCHETTE", result.vaschette), ("SUBSTRATO", result.substrato)):
        print(f"{etichetta}_MOVIMENTO_ID={r.movimento_id.value}", file=stdout)
        print(f"{etichetta}_ARTICOLO_ID={r.articolo_id.value}", file=stdout)
        print(f"{etichetta}_QUANTITA={r.quantita}", file=stdout)
        print(f"{etichetta}_STOCK_DISPONIBILE={r.stock_disponibile}", file=stdout)
        print(f"{etichetta}_OUTCOME={r.outcome}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
