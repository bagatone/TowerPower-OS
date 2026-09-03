"""Atomic PostgreSQL writer for Semente Commissioning V1."""

from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.semente_commissioning.errors import (
    SementeCommitRolledBackError, SementeConcurrencyConflictError,
    SementeDuplicateError, SementeIdempotencyConflictError,
    SementeReconciliationRequiredError,
)
from ...application.semente_commissioning.models import (
    CommissionSemente, CommissionSementeResult,
)
from .connection import PostgreSQLConnectionFactory

SCOPE = "SEMENTE_COMMISSIONING_V1"


class PostgreSQLSementeCommissioningWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def commission(self, command: CommissionSemente) -> CommissionSementeResult:
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            reservation_id, replay = self._reserve_or_replay(cursor, command)
            if replay is not None:
                connection.rollback()
                return replay
            if reservation_id is None:
                raise SementeReconciliationRequiredError(
                    "Reservation idempotency non riconciliabile."
                )
            self._assert_not_duplicate(cursor, command)
            cursor.execute(
                """INSERT INTO tpo.sementi
                   (fornitore,referenza_commerciale,marca,formato,trattamento,
                    certificazioni,attiva,created_by,updated_at,updated_by,version)
                   VALUES (%s,%s,%s,%s,%s,%s,true,%s,CURRENT_TIMESTAMP,%s,0)
                   RETURNING id,created_at""",
                (command.fornitore, command.referenza_commerciale, command.marca,
                 command.formato, command.trattamento, command.certificazioni,
                 command.authority.actor.value, command.authority.actor.value),
            )
            semente_pk, recorded_at = cursor.fetchone()
            cursor.execute(
                """UPDATE tpo.semente_commissioning_requests
                   SET semente_id=%s,outcome='COMMITTED',recorded_at=%s
                   WHERE id=%s AND operation_scope=%s
                     AND canonical_payload_hash=%s AND outcome='RESERVED'
                     AND semente_id IS NULL""",
                (semente_pk, recorded_at, reservation_id, SCOPE,
                 command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise SementeConcurrencyConflictError(
                    "Reservation idempotency non aggiornabile."
                )
            self._audit(cursor, semente_pk, command, recorded_at)
            result = _result(semente_pk, command, recorded_at, "INSERTED")
            try:
                connection.commit()
            except Exception as exc:
                raise SementeReconciliationRequiredError(
                    "Esito commit SEMENTE da riconciliare."
                ) from exc
            committed = True
            return result
        except (SementeDuplicateError, SementeIdempotencyConflictError,
                SementeConcurrencyConflictError, SementeReconciliationRequiredError):
            raise
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise SementeCommitRolledBackError(
                "Commissioning SEMENTE fallito con rollback certo."
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
    def _reserve_or_replay(
        cursor: Any, command: CommissionSemente,
    ) -> tuple[int | None, CommissionSementeResult | None]:
        cursor.execute(
            """INSERT INTO tpo.semente_commissioning_requests
               (operation_scope,idempotency_key,canonical_payload_hash,
                semente_id,outcome,recorded_at,created_by)
               VALUES (%s,%s,%s,NULL,'RESERVED',CURRENT_TIMESTAMP,%s)
               ON CONFLICT (operation_scope,idempotency_key) DO NOTHING
               RETURNING id""",
            (SCOPE, command.authority.idempotency_key,
             command.canonical_payload_hash, command.authority.actor.value),
        )
        row = cursor.fetchone()
        if row is not None:
            return row[0], None
        return None, PostgreSQLSementeCommissioningWriter._replay(cursor, command)

    @staticmethod
    def _replay(cursor: Any, command: CommissionSemente) -> CommissionSementeResult:
        cursor.execute(
            """SELECT r.canonical_payload_hash,r.outcome,s.id,s.fornitore,
                      s.referenza_commerciale,s.marca,s.formato,s.trattamento,
                      s.certificazioni,s.attiva,r.recorded_at
               FROM tpo.semente_commissioning_requests r
               JOIN tpo.sementi s ON s.id=r.semente_id
               WHERE r.operation_scope=%s AND r.idempotency_key=%s
               FOR UPDATE OF r""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if row is None:
            raise SementeReconciliationRequiredError(
                "Reservation idempotency concorrente non leggibile."
            )
        if row[0] != command.canonical_payload_hash:
            raise SementeIdempotencyConflictError("Stessa idempotency key con payload differente.")
        if row[1] != "COMMITTED":
            raise SementeReconciliationRequiredError(
                "Reservation idempotency priva di risultato committed."
            )
        return CommissionSementeResult(
            row[2], "COMPATIBLE_REPLAY", row[3], row[4], row[5], row[6], row[7], row[8],
            row[9], row[10],
        )

    @staticmethod
    def _assert_not_duplicate(cursor: Any, command: CommissionSemente) -> None:
        cursor.execute(
            """SELECT id FROM tpo.sementi
               WHERE lower(btrim(fornitore))=lower(btrim(%s))
                 AND lower(btrim(referenza_commerciale))=lower(btrim(%s))
               FOR UPDATE""",
            (command.fornitore, command.referenza_commerciale),
        )
        if cursor.fetchone() is not None:
            raise SementeDuplicateError(
                "SEMENTE già commissionata con altra request authority."
            )

    @staticmethod
    def _audit(cursor: Any, semente_pk: int, command: CommissionSemente, recorded_at: Any) -> None:
        after = {
            "internal_id": semente_pk,
            "fornitore": command.fornitore,
            "referenza_commerciale": command.referenza_commerciale,
            "marca": command.marca, "formato": command.formato,
            "trattamento": command.trattamento, "certificazioni": command.certificazioni,
            "attiva": True,
            "idempotency_key": command.authority.idempotency_key,
            "canonical_payload_hash": command.canonical_payload_hash,
        }
        cursor.execute(
            """INSERT INTO tpo.audit_eventi
               (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                after_data,correlation_id,provenance)
               VALUES (%s,%s,'SEMENTE',NULL,'INSERT',%s,%s,%s,%s)""",
            (recorded_at, command.authority.actor.value,
             command.authority.reason, Jsonb(after), command.authority.correlation_id,
             json.dumps({"boundary": "semente-commissioning-v1"}, sort_keys=True)),
        )

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "")
        if name == "uq_semente_commissioning_request_key":
            return SementeReconciliationRequiredError(
                "Collisione idempotency inattesa da riconciliare."
            )
        if name == "uq_sementi_fornitore_referenza_normalized":
            return SementeDuplicateError("SEMENTE già commissionata.")
        return SementeCommitRolledBackError("Vincolo SEMENTE non soddisfatto.")


def _result(semente_pk: int, command: CommissionSemente,
            recorded_at: Any, outcome: str) -> CommissionSementeResult:
    return CommissionSementeResult(
        semente_pk, outcome, command.fornitore, command.referenza_commerciale,
        command.marca, command.formato, command.trattamento, command.certificazioni,
        True, recorded_at,
    )
