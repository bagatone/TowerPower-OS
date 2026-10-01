"""Thin CLI adapter per il commissioning di un protocollo agronomico
completo (USO_PRODUTTIVO + CULTIVAR + CULTIVAR_USO + PROTOCOLLO +
PROTOCOLLO_VERSIONE in un'unica autorita' atomica e idempotente).

Il servizio applicativo e il writer PostgreSQL esistevano gia'
(`AgronomicProtocolCommissioningService`, gia' testato a livello di
dominio/applicazione/integrazione) ma non erano collegati a nessun
comando CLI -- scoperto il 2026-10-01 mentre si cercava di seminare
Rucola e Pak Choi, prive di protocollo di coltivazione a sistema pur
avendo gia' una VARIETA onboardata. Questo file e' solo il collegamento
mancante, nessuna nuova regola di dominio."""
from argparse import Namespace
from datetime import date, time
from decimal import Decimal
from typing import TextIO

from ..application.agronomic_commissioning.errors import (
    AgronomicCommissioningError, InvalidAgronomicCommissioningCommandError,
)
from ..application.agronomic_commissioning.models import CommissionAgronomicProtocolCommand
from ..bootstrap import build_agronomic_protocol_commissioner
from ..domain.identifiers import ActorId, ProtocolloVersioneId, VarietaId
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode


def run_protocollo_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    try:
        command = CommissionAgronomicProtocolCommand(
            variety_id=VarietaId(args.variety_id),
            variety_name=args.variety_name,
            cultivar_name=args.cultivar_name,
            productive_use_code=args.productive_use_code,
            productive_use_name=args.productive_use_name,
            protocol_name=args.protocol_name,
            protocol_version_id=ProtocolloVersioneId(args.protocol_version_id),
            version=args.version,
            valid_from=date.fromisoformat(args.valid_from),
            valid_to=date.fromisoformat(args.valid_to) if args.valid_to else None,
            hydration_hours=Decimal(args.hydration_hours),
            planned_sowing_time=time.fromisoformat(args.planned_sowing_time),
            target_harvest_time=time.fromisoformat(args.target_harvest_time),
            germination_days=args.germination_days,
            light_growth_days=args.light_growth_days,
            seed_grams_per_set=Decimal(args.seed_grams_per_set),
            expected_yield=Decimal(args.expected_yield),
            production_granularity=Decimal(args.production_granularity),
            harvest_min_lead_days=args.harvest_min_lead_days,
            harvest_max_lead_days=args.harvest_max_lead_days,
            temporal_buffer_minutes=args.temporal_buffer_minutes,
            content=args.content,
            motivation=args.motivation,
            evidence=args.evidence,
            provenance=args.provenance,
            actor=ActorId(args.actor),
            reason=args.reason,
            correlation_id=args.correlation_id,
        )
        result = build_agronomic_protocol_commissioner(
            PostgreSQLSettings.from_environment()
        ).commission(command)
    except (ValueError, TypeError, AgronomicCommissioningError) as exc:
        code = "AGRONOMIC_PROTOCOL_INPUT_INVALID" if isinstance(
            exc, (ValueError, TypeError, InvalidAgronomicCommissioningCommandError),
        ) else "AGRONOMIC_PROTOCOL_COMMISSIONING_FAILED"
        print(f"AGRONOMIC_PROTOCOL_COMMISSIONING_FAILED: {code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_INPUT_INVALID
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    print("STATUS: COMMITTED", file=stdout)
    print("ENTITY: PROTOCOLLO_VERSIONE", file=stdout)
    print(f"PUBLIC_ID: {result.command.protocol_version_id.value}", file=stdout)
    print(f"VARIETY: {result.command.variety_id.value}", file=stdout)
    print(f"CULTIVAR: {result.command.cultivar_name}", file=stdout)
    print(f"APPROVED_AT: {result.approved_at.isoformat()}", file=stdout)
    print(f"INSERTED_ENTITIES: {','.join(result.inserted_entities) or '(nessuna - replay)'}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
