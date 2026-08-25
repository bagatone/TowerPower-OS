"""Writer PostgreSQL atomico Semina Lifecycle Event Authority V1."""
from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.semina_lifecycle.errors import (
    SeminaAlreadyClosedError, SeminaLifecycleCommitOutcomeUncertainError,
    SeminaLifecycleCommitRolledBackError, SeminaLifecycleIdempotencyConflictError,
    SeminaLifecycleReconciliationRequiredError, SeminaLifecycleTimestampRegressionError,
    SeminaNotFoundError, SeminaTransitionInvalidError, SeminaVersionConflictError,
)
from ...application.semina_lifecycle.models import (
    SeminaFinalOutcome, TransitionSemina, TransitionSeminaResult, validate_transition,
)
from ...domain.identifiers import SeminaId
from ...domain.states import SeminaState
from .connection import PostgreSQLConnectionFactory

SCOPE = "SEMINA_LIFECYCLE_TRANSITION_V1"
DOMAIN_TO_POSTGRESQL_OUTCOME = {
    SeminaFinalOutcome.RACCOLTA_COMPLETA: "RACCOLTA_COMPLETA",
    SeminaFinalOutcome.RACCOLTA_PARZIALE_CON_SCARTO: "RACCOLTA_PARZIALE_CON_SCARTO",
    SeminaFinalOutcome.SCARTO_TOTALE: "SCARTO_TOTALE",
    SeminaFinalOutcome.INTERRUZIONE: "INTERRUZIONE",
}
POSTGRESQL_TO_DOMAIN_OUTCOME = {
    token: outcome for outcome, token in DOMAIN_TO_POSTGRESQL_OUTCOME.items()
}


def outcome_to_postgresql(outcome: SeminaFinalOutcome | None) -> str | None:
    if outcome is None:
        return None
    try:
        return DOMAIN_TO_POSTGRESQL_OUTCOME[outcome]
    except (KeyError, TypeError) as exc:
        raise SeminaLifecycleReconciliationRequiredError(
            "Esito finale domain non mappato."
        ) from exc


def outcome_from_postgresql(token: str | None) -> SeminaFinalOutcome | None:
    if token is None:
        return None
    try:
        return POSTGRESQL_TO_DOMAIN_OUTCOME[token]
    except KeyError as exc:
        raise SeminaLifecycleReconciliationRequiredError(
            "Esito finale persistito non riconosciuto."
        ) from exc


class PostgreSQLSeminaLifecycleWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def transition(self, command: TransitionSemina) -> TransitionSeminaResult:
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            reservation, recorded_at, replay = self._reserve_or_replay(cursor, command)
            if replay is not None:
                connection.rollback()
                return replay
            if reservation is None or recorded_at is None:
                raise SeminaLifecycleReconciliationRequiredError("Reservation lifecycle non riconciliabile.")
            semina = self._lock_semina(cursor, command)
            current = SeminaState(semina[2])
            if current is SeminaState.CHIUSA:
                raise SeminaAlreadyClosedError("SEMINA già CHIUSA.")
            if current is command.target_state:
                raise SeminaTransitionInvalidError("Transizione SEMINA già applicata.")
            if semina[3] != command.expected_semina_version:
                raise SeminaVersionConflictError("Versione SEMINA non corrente.")
            validate_transition(current, command.target_state)
            if command.effective_at < semina[4]:
                raise SeminaLifecycleTimestampRegressionError("effective_at precede data_avvio.")
            cursor.execute(
                """SELECT effective_at FROM tpo.semina_lifecycle_eventi
                   WHERE semina_id=%s ORDER BY effective_at DESC,id DESC LIMIT 1 FOR UPDATE""",
                (semina[0],),
            )
            latest = cursor.fetchone()
            if latest is not None and command.effective_at <= latest[0]:
                raise SeminaLifecycleTimestampRegressionError("effective_at non è strettamente monotono.")
            version_after = semina[3] + 1
            provenance = {field: source.value for field, source in command.provenance}
            cursor.execute(
                """INSERT INTO tpo.semina_lifecycle_eventi
                   (request_id,semina_id,semina_public_id,from_state,to_state,esito_finale,
                    effective_at,recorded_at,version_before,version_after,actor,reason,
                    correlation_id,provenance)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                (reservation, semina[0], command.semina_public_id.value, current.value,
                 command.target_state.value,
                 outcome_to_postgresql(command.final_outcome),
                 command.effective_at, recorded_at, semina[3], version_after,
                 command.authority.actor.value, command.authority.reason,
                 command.authority.correlation_id, Jsonb(provenance)),
            )
            event_id = cursor.fetchone()[0]
            cursor.execute(
                """UPDATE tpo.semine SET stato=%s,esito_finale=%s,version=version+1
                   WHERE id=%s AND public_id=%s AND version=%s AND stato=%s""",
                (command.target_state.value,
                 outcome_to_postgresql(command.final_outcome),
                 semina[0], command.semina_public_id.value, semina[3], current.value),
            )
            if cursor.rowcount != 1:
                raise SeminaVersionConflictError("SEMINA modificata concorrente.")
            before = {"state": current.value, "final_outcome": semina[5],
                      "effective_at": latest[0].isoformat() if latest else None,
                      "version": semina[3]}
            after = {"state": command.target_state.value,
                     "final_outcome": command.final_outcome.value if command.final_outcome else None,
                     "effective_at": command.effective_at.isoformat(),
                     "version": version_after, "lifecycle_event_internal_id": event_id}
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'SEMINA',%s,'STATE_TRANSITION',%s,%s,%s,%s,%s)""",
                (recorded_at, command.authority.actor.value, command.semina_public_id.value,
                 command.authority.reason, Jsonb(before), Jsonb(after),
                 command.authority.correlation_id,
                 json.dumps({"boundary": "semina-lifecycle-transition-v1",
                             "facts": provenance}, sort_keys=True)),
            )
            cursor.execute(
                """UPDATE tpo.semina_lifecycle_transition_requests
                   SET outcome='COMMITTED',result_event_id=%s
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (event_id, reservation, command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise SeminaLifecycleReconciliationRequiredError("Reservation lifecycle non aggiornabile.")
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = TransitionSeminaResult(
                command.semina_public_id, current, command.target_state,
                command.final_outcome, command.effective_at, recorded_at,
                semina[3], version_after, "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise SeminaLifecycleCommitOutcomeUncertainError(
                    "Esito commit lifecycle SEMINA da riconciliare."
                ) from exc
            committed = True
            return result
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise SeminaLifecycleCommitRolledBackError(
                "Transizione lifecycle SEMINA fallita con rollback certo."
            ) from exc
        finally:
            if not committed:
                try: connection.rollback()
                except Exception: pass
            if cursor is not None:
                try: cursor.close()
                except Exception: pass
            try: connection.close()
            except Exception: pass

    @staticmethod
    def _reserve_or_replay(cursor: Any, command: TransitionSemina):
        cursor.execute(
            """INSERT INTO tpo.semina_lifecycle_transition_requests
               (operation_scope,idempotency_key,canonical_payload_hash,outcome,recorded_at,created_by)
               VALUES (%s,%s,%s,'RESERVED',CURRENT_TIMESTAMP,%s)
               ON CONFLICT (operation_scope,idempotency_key) DO NOTHING
               RETURNING id,recorded_at""",
            (SCOPE, command.authority.idempotency_key, command.canonical_payload_hash,
             command.authority.actor.value),
        )
        row = cursor.fetchone()
        if row:
            return row[0], row[1], None
        cursor.execute(
            """SELECT r.canonical_payload_hash,r.outcome,e.semina_public_id,e.from_state,
                      e.to_state,e.esito_finale,e.effective_at,e.recorded_at,
                      e.version_before,e.version_after
               FROM tpo.semina_lifecycle_transition_requests r
               LEFT JOIN tpo.semina_lifecycle_eventi e
                 ON e.id=r.result_event_id AND e.request_id=r.id
               WHERE r.operation_scope=%s AND r.idempotency_key=%s FOR UPDATE OF r""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if not row:
            raise SeminaLifecycleReconciliationRequiredError("Reservation concorrente non leggibile.")
        if row[0] != command.canonical_payload_hash:
            raise SeminaLifecycleIdempotencyConflictError("Stessa idempotency key con payload differente.")
        if row[1] != "COMMITTED" or row[2] is None:
            raise SeminaLifecycleReconciliationRequiredError("Reservation priva di evento committed.")
        return None, None, TransitionSeminaResult(
            SeminaId(row[2]), SeminaState(row[3]), SeminaState(row[4]),
            outcome_from_postgresql(row[5]), row[6], row[7],
            row[8], row[9], "COMPATIBLE_REPLAY",
        )

    @staticmethod
    def _lock_semina(cursor: Any, command: TransitionSemina):
        cursor.execute(
            """SELECT id,public_id,stato,version,data_avvio,esito_finale
               FROM tpo.semine WHERE public_id=%s FOR UPDATE""",
            (command.semina_public_id.value,),
        )
        row = cursor.fetchone()
        if not row:
            raise SeminaNotFoundError("SEMINA inesistente.")
        return row

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if name == "uq_semina_lifecycle_request_key":
            return SeminaLifecycleReconciliationRequiredError("Collisione idempotency da riconciliare.")
        if name.startswith("ck_semina_lifecycle_event"):
            return SeminaTransitionInvalidError("Vincolo lifecycle SEMINA non soddisfatto.")
        return SeminaLifecycleCommitRolledBackError("Vincolo lifecycle SEMINA non soddisfatto.")
