"""Writer PostgreSQL atomico per Articolo Commissioning Boundary V1.

Autorità: docs/architecture/ARTICOLO_AUTHORITY_FREEZE.md. Commissiona un nuovo
ARTICOLO (materiali della catena: substrati, fertilizzante, packaging, ecc. --
distinto da VARIETA). Nessuna unicità di business-key imposta su
denominazione (nessuna richiesta da alcuna authority congelata).
"""
from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb
import json

from ...application.articolo.errors import (
    ArticoloCommitOutcomeUncertainError,
    ArticoloCommitRolledBackError,
    ArticoloIdempotencyConflictError,
    ArticoloIdentityUnavailableError,
    ArticoloPersistenceInvariantError,
    ArticoloReconciliationRequiredError,
)
from ...application.articolo.models import CommissionArticolo, CommissionArticoloResult
from ...domain.identifiers import ArticoloId
from .connection import PostgreSQLConnectionFactory

SCOPE = "ARTICOLO_COMMISSIONING_V1"


class PostgreSQLArticoloWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def commission(self, command: CommissionArticolo) -> CommissionArticoloResult:
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            reservation, replay = self._reserve_or_replay(cursor, command)
            if replay is not None:
                connection.rollback()
                return replay
            if reservation is None:
                raise ArticoloReconciliationRequiredError(
                    "Reservation ARTICOLO non riconciliabile."
                )
            public_id, sequence = self._allocate(cursor)
            cursor.execute(
                """INSERT INTO tpo.articoli
                   (public_id,denominazione,unita_misura,created_by)
                   VALUES (%s,%s,%s,%s) RETURNING id,created_at""",
                (public_id.value, command.denominazione, command.unita_misura,
                 command.authority.actor.value),
            )
            articolo_pk, recorded_at = cursor.fetchone()
            after = {
                "public_id": public_id.value,
                "denominazione": command.denominazione,
                "unita_misura": command.unita_misura,
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'ARTICOLO',%s,'INSERT',%s,NULL,%s,%s,%s)""",
                (recorded_at, command.authority.actor.value, public_id.value,
                 command.authority.reason, Jsonb(after), command.authority.correlation_id,
                 json.dumps({"boundary": "articolo-commissioning-v1",
                             "idempotency_key": command.authority.idempotency_key},
                            sort_keys=True)),
            )
            cursor.execute(
                """UPDATE tpo.articolo_commissioning_requests
                   SET articolo_id=%s,result_public_id=%s,outcome='COMMITTED'
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (articolo_pk, public_id.value, reservation, command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise ArticoloReconciliationRequiredError(
                    "Reservation ARTICOLO non aggiornabile."
                )
            cursor.execute(
                """UPDATE tpo.id_sequences SET next_value=%s,version=version+1,
                   updated_at=%s,updated_by=%s WHERE sequence_name=%s
                   AND identifier_type=%s AND prefix=%s AND next_value=%s AND version=%s""",
                (sequence[3] + 1, recorded_at, command.authority.actor.value,
                 ArticoloId.sequence_name, ArticoloId.__name__, ArticoloId.prefix,
                 sequence[3], sequence[4]),
            )
            if cursor.rowcount != 1:
                raise ArticoloIdentityUnavailableError("Conflitto contatore ARTICOLO_ID.")
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = CommissionArticoloResult(
                public_id, command.denominazione, command.unita_misura, recorded_at, "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise ArticoloCommitOutcomeUncertainError(
                    "Esito commit ARTICOLO da riconciliare tramite idempotency_key."
                ) from exc
            committed = True
            return result
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise ArticoloCommitRolledBackError(
                "Commissioning ARTICOLO fallito con rollback certo."
            ) from exc
        finally:
            if not committed:
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

    @staticmethod
    def _reserve_or_replay(cursor: Any, command: CommissionArticolo):
        cursor.execute(
            """INSERT INTO tpo.articolo_commissioning_requests
               (operation_scope,idempotency_key,canonical_payload_hash,articolo_id,
                result_public_id,outcome,recorded_at,created_by)
               VALUES (%s,%s,%s,NULL,NULL,'RESERVED',CURRENT_TIMESTAMP,%s)
               ON CONFLICT (operation_scope,idempotency_key) DO NOTHING
               RETURNING id""",
            (SCOPE, command.authority.idempotency_key, command.canonical_payload_hash,
             command.authority.actor.value),
        )
        row = cursor.fetchone()
        if row is not None:
            return row[0], None
        cursor.execute(
            """SELECT q.canonical_payload_hash,q.outcome,a.public_id,a.denominazione,
                      a.unita_misura,q.recorded_at
               FROM tpo.articolo_commissioning_requests q
               LEFT JOIN tpo.articoli a ON a.id=q.articolo_id
               WHERE q.operation_scope=%s AND q.idempotency_key=%s FOR UPDATE OF q""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if row is None:
            raise ArticoloReconciliationRequiredError(
                "Reservation ARTICOLO concorrente non leggibile."
            )
        if row[0] != command.canonical_payload_hash:
            raise ArticoloIdempotencyConflictError(
                "Stessa idempotency key con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise ArticoloReconciliationRequiredError(
                "Reservation ARTICOLO priva di risultato committed."
            )
        return None, CommissionArticoloResult(
            ArticoloId(row[2]), row[3], row[4], row[5], "COMPATIBLE_REPLAY",
        )

    @staticmethod
    def _allocate(cursor: Any):
        cursor.execute(
            """SELECT sequence_name,identifier_type,prefix,next_value,version
               FROM tpo.id_sequences WHERE sequence_name=%s FOR UPDATE""",
            (ArticoloId.sequence_name,),
        )
        row = cursor.fetchone()
        if not row or row[1] != ArticoloId.__name__ or row[2] != ArticoloId.prefix:
            raise ArticoloIdentityUnavailableError("ARTICOLO_ID assente o incompatibile.")
        try:
            return ArticoloId(f"{row[2]}-{row[3]:06d}"), row
        except Exception as exc:
            raise ArticoloIdentityUnavailableError("ARTICOLO_ID malformata.") from exc

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if name == "uq_articolo_commissioning_request_key":
            return ArticoloReconciliationRequiredError(
                "Collisione idempotency inattesa da riconciliare."
            )
        if name in {"articoli_public_id_key", "ck_articoli_public_id_format"}:
            return ArticoloIdentityUnavailableError("Collisione ART identity.")
        if name.startswith("ck_articoli_"):
            return ArticoloPersistenceInvariantError("Vincolo ARTICOLO non soddisfatto.")
        return ArticoloCommitRolledBackError("Vincolo ARTICOLO non soddisfatto.")
