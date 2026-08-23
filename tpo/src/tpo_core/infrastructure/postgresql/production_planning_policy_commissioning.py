"""PostgreSQL append-only writer for Production Planning policy commissioning."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg

from ...application.policy_commissioning.errors import (
    PolicyCommissioningConflictError,
    PolicyCommissioningOutcomeUncertain,
    PolicyCommissioningPersistenceError,
)
from ...application.policy_commissioning.models import (
    CommissionProductionPlanningPolicyCommand,
    CommissionedProductionPlanningPolicy,
)
from ...domain.identifiers import ActorId
from .connection import PostgreSQLConnectionFactory


class PostgreSQLProductionPlanningPolicyCommissioningWriter:
    """Inserts one immutable policy version or proves a compatible replay."""

    def __init__(self, connection_factory: PostgreSQLConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def commission(
        self, policy: CommissionedProductionPlanningPolicy,
    ) -> CommissionedProductionPlanningPolicy:
        connection = self._connection_factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            command = policy.command
            cursor.execute(
                """INSERT INTO tpo.production_planning_policy_versions
                     (policy_set_code,numero_versione,harvest_target_strategy,
                      buffer_quantitativo_tipo,buffer_quantitativo_valore,
                      priority_policy_code,planning_algorithm_version,
                      valida_dal,valida_al,provenance,evidenze,approved_at,
                      approved_by,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (policy_set_code,numero_versione) DO NOTHING
                   RETURNING approved_at""",
                (
                    command.policy_set_code,
                    command.version,
                    command.harvest_target_strategy,
                    command.quantitative_buffer_type,
                    command.quantitative_buffer_value,
                    command.priority_policy_code,
                    command.planning_algorithm_version,
                    command.valid_from,
                    command.valid_to,
                    command.provenance,
                    command.evidence,
                    policy.approved_at,
                    command.actor.value,
                    command.actor.value,
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                persisted = self._load(cursor, command)
                if persisted is None or not _compatible(command, persisted):
                    raise PolicyCommissioningConflictError(
                        "La policy richiesta esiste con un payload differente."
                    )
                result = _result(command, persisted[11])
            else:
                result = CommissionedProductionPlanningPolicy(command, inserted[0])
            try:
                connection.commit()
            except Exception as exc:
                raise PolicyCommissioningOutcomeUncertain(
                    "Esito del commit di commissioning da riconciliare."
                ) from exc
            committed = True
            return result
        except PolicyCommissioningConflictError:
            raise
        except psycopg.IntegrityError as exc:
            raise PolicyCommissioningConflictError(
                "Vincolo della policy commissionata non soddisfatto."
            ) from exc
        except psycopg.Error as exc:
            raise PolicyCommissioningPersistenceError(
                "Commissioning PostgreSQL non completato con rollback certo."
            ) from exc
        finally:
            _cleanup(cursor, connection, rollback=not committed)

    @staticmethod
    def _load(
        cursor: Any, command: CommissionProductionPlanningPolicyCommand,
    ) -> tuple[Any, ...] | None:
        cursor.execute(
            """SELECT policy_set_code,numero_versione,harvest_target_strategy,
                      buffer_quantitativo_tipo,buffer_quantitativo_valore,
                      priority_policy_code,planning_algorithm_version,
                      valida_dal,valida_al,provenance,evidenze,approved_at,
                      approved_by,created_by
               FROM tpo.production_planning_policy_versions
               WHERE policy_set_code=%s AND numero_versione=%s""",
            (command.policy_set_code, command.version),
        )
        return cursor.fetchone()


def _compatible(
    command: CommissionProductionPlanningPolicyCommand,
    row: tuple[Any, ...],
) -> bool:
    persisted_buffer = row[4]
    if persisted_buffer is not None:
        persisted_buffer = Decimal(persisted_buffer)
    return (
        row[0] == command.policy_set_code
        and row[1] == command.version
        and row[2] == command.harvest_target_strategy
        and row[3] == command.quantitative_buffer_type
        and persisted_buffer == command.quantitative_buffer_value
        and row[5] == command.priority_policy_code
        and row[6] == command.planning_algorithm_version
        and row[7] == command.valid_from
        and row[8] == command.valid_to
        and row[9] == command.provenance
        and row[10] == command.evidence
        and row[12] == command.actor.value
        and row[13] == command.actor.value
    )


def _result(
    command: CommissionProductionPlanningPolicyCommand, approved_at: datetime,
) -> CommissionedProductionPlanningPolicy:
    return CommissionedProductionPlanningPolicy(
        CommissionProductionPlanningPolicyCommand(
            policy_set_code=command.policy_set_code,
            version=command.version,
            valid_from=command.valid_from,
            valid_to=command.valid_to,
            priority_policy_code=command.priority_policy_code,
            planning_algorithm_version=command.planning_algorithm_version,
            quantitative_buffer_type=command.quantitative_buffer_type,
            quantitative_buffer_value=command.quantitative_buffer_value,
            harvest_target_strategy=command.harvest_target_strategy,
            actor=ActorId(command.actor.value),
            provenance=command.provenance,
            evidence=command.evidence,
        ),
        approved_at,
    )


def _cleanup(cursor: Any, connection: Any, *, rollback: bool) -> None:
    if rollback:
        try:
            connection.rollback()
        except Exception:
            pass
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            pass
    try:
        connection.close()
    except Exception:
        pass
