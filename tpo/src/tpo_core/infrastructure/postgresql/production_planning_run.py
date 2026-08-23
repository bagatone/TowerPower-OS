"""PostgreSQL adapter for the frozen Production Planning RUN boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg

from ...application.production_planning.errors import ProductionPlanningError
from ...application.production_planning.models import (
    PolicyVersionReference,
    ProductionPlanningReconciliationRequiredResult,
    ProductionPlanningRunSnapshot,
    PublicId,
    RunMessage,
)
from .connection import PostgreSQLConnectionFactory


class PostgreSQLProductionPlanningRunAdapter:
    """Owns one short transaction for each frozen RUN mutation."""

    def __init__(self, connection_factory: PostgreSQLConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def open(
        self, *, public_id: PublicId, policy: PolicyVersionReference,
        business_at: datetime, started_at: datetime, created_by: str,
    ) -> ProductionPlanningRunSnapshot:
        def mutation(cursor: Any) -> ProductionPlanningRunSnapshot:
            cursor.execute(
                """SELECT id FROM tpo.production_planning_policy_versions
                   WHERE policy_set_code=%s AND numero_versione=%s
                     AND valida_dal<=%s::date
                     AND (valida_al IS NULL OR %s::date<valida_al)
                   ORDER BY id""",
                (policy.policy_set_code, policy.version, business_at, business_at),
            )
            policies = cursor.fetchall()
            if len(policies) != 1:
                raise _input("POLICY_NOT_EXACT", "Planning Policy richiesta assente o ambigua.")
            cursor.execute(
                """INSERT INTO tpo.production_planning_runs
                     (public_id,policy_version_id,business_at,state,started_at,created_by,version)
                   VALUES (%s,%s,%s,'OPEN',%s,%s,0)
                   RETURNING public_id,version,state""",
                (public_id.value, policies[0][0], business_at, started_at, created_by),
            )
            row = cursor.fetchone()
            if row is None:
                raise _internal("RUN_OPEN_FAILED", "Apertura RUN non confermata.")
            return ProductionPlanningRunSnapshot(PublicId(row[0]), row[1], row[2])

        return self._mutate(mutation, duplicate_code="RUN_ALREADY_EXISTS")

    def finalize_failure(
        self, *, run: ProductionPlanningRunSnapshot, completed_at: datetime,
        error: ProductionPlanningError, messages: tuple[RunMessage, ...],
    ) -> None:
        def mutation(cursor: Any) -> None:
            run_pk = self._transition(
                cursor, run=run, target="FAILED", completed_at=completed_at,
            )
            for message in messages:
                cursor.execute(
                    """INSERT INTO tpo.production_planning_run_messaggi
                         (planning_run_id,posizione,tipo,failure_category,codice,messaggio,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (run_pk, message.position, message.message_type,
                     message.failure_category, message.code, message.message,
                     message.created_at),
                )

        self._mutate(mutation)

    def require_reconciliation(
        self, *, run: ProductionPlanningRunSnapshot, business_at: datetime,
        observed_at: datetime, correlation_id: str,
        error: ProductionPlanningError,
    ) -> ProductionPlanningReconciliationRequiredResult:
        def mutation(cursor: Any) -> ProductionPlanningReconciliationRequiredResult:
            run_pk = self._transition(
                cursor, run=run, target="RECONCILIATION_REQUIRED",
                completed_at=observed_at,
            )
            cursor.execute(
                """INSERT INTO tpo.production_planning_run_messaggi
                     (planning_run_id,posizione,tipo,failure_category,codice,messaggio,created_at)
                   VALUES (%s,1,'ERROR','RECONCILIATION_REQUIRED',%s,%s,%s)""",
                (run_pk, error.code, error.safe_message, observed_at),
            )
            return ProductionPlanningReconciliationRequiredResult(
                planning_run_public_id=run.public_id,
                run_state="RECONCILIATION_REQUIRED", business_at=business_at,
                observed_at=observed_at, correlation_id=correlation_id,
                failure_category="RECONCILIATION_REQUIRED", code=error.code,
                message=error.safe_message,
            )

        return self._mutate(mutation)

    @staticmethod
    def _transition(
        cursor: Any, *, run: ProductionPlanningRunSnapshot, target: str,
        completed_at: datetime,
    ) -> int:
        cursor.execute(
            """UPDATE tpo.production_planning_runs
               SET state=%s,completed_at=%s,version=version+1
               WHERE public_id=%s AND state='OPEN' AND version=%s
               RETURNING id""",
            (target, completed_at, run.public_id.value, run.expected_version),
        )
        row = cursor.fetchone()
        if row is None:
            raise ProductionPlanningError(
                "CONCURRENCY_CONFLICT", "RUN_STATE_CONFLICT",
                "RUN assente, non OPEN o modificata concorrentemente.",
            )
        return row[0]

    def _mutate(self, operation, *, duplicate_code: str = "RUN_MUTATION_CONFLICT"):
        connection = self._connection_factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            result = operation(cursor)
            connection.commit()
            committed = True
            return result
        except ProductionPlanningError:
            raise
        except psycopg.errors.UniqueViolation as exc:
            raise ProductionPlanningError(
                "CONCURRENCY_CONFLICT", duplicate_code,
                "Conflitto univoco sulla RUN Production Planning.",
            ) from exc
        except psycopg.IntegrityError as exc:
            raise _input("RUN_CONSTRAINT_VIOLATION", "Mutation RUN non valida.") from exc
        except psycopg.Error as exc:
            raise _internal("RUN_PERSISTENCE_FAILED", "Mutation RUN non completata.") from exc
        finally:
            _cleanup(cursor, connection, rollback=not committed)


def _input(code: str, message: str) -> ProductionPlanningError:
    return ProductionPlanningError("PLANNING_INPUT_INVALID", code, message)


def _internal(code: str, message: str) -> ProductionPlanningError:
    return ProductionPlanningError("INTERNAL_ERROR", code, message)


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
