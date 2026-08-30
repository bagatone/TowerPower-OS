"""Writer PostgreSQL atomico per Raccolta Recording Boundary V1."""
from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.raccolta.errors import (
    RaccoltaCommitOutcomeUncertainError, RaccoltaCommitRolledBackError,
    RaccoltaIdempotencyConflictError, RaccoltaIdentityUnavailableError,
    RaccoltaPersistenceInvariantError, RaccoltaReconciliationRequiredError,
    RaccoltaSeminaNotFoundError, RaccoltaSeminaStateError,
    RaccoltaTraceabilityUnavailableError,
)
from ...application.raccolta.models import RecordRaccolta, RecordRaccoltaResult
from ...domain.identifiers import RaccoltaId, SeminaId
from ...domain.quantities import Quantity, UnitOfMeasure
from ...domain.traceability import SeminaTraceabilityCode
from .connection import PostgreSQLConnectionFactory

SCOPE = "RACCOLTA_RECORDING_V1"


class PostgreSQLRaccoltaWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def record(self, command: RecordRaccolta) -> RecordRaccoltaResult:
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
                raise RaccoltaReconciliationRequiredError("Reservation RACCOLTA non riconciliabile.")
            semina = self._lock_semina(cursor, command)
            if semina[2] != "PRONTA_ALLA_RACCOLTA":
                raise RaccoltaSeminaStateError("SEMINA non PRONTA_ALLA_RACCOLTA.")
            try:
                traceability = SeminaTraceabilityCode(semina[3])
            except Exception as exc:
                raise RaccoltaTraceabilityUnavailableError(
                    "SEMINA priva di tracciabilità canonica valida."
                ) from exc
            public_id, sequence = self._allocate(cursor)
            cursor.execute(
                """INSERT INTO tpo.raccolte
                   (public_id,semina_id,data_raccolta,quantita,unita_misura,
                    operatore,destinazione_prevista,note,created_by)
                   VALUES (%s,%s,%s,%s,'SET',NULL,NULL,%s,%s)
                   RETURNING id,created_at""",
                (public_id.value, semina[0], command.effective_at,
                 command.quantity.value, command.notes, command.authority.actor.value),
            )
            raccolta_pk, recorded_at = cursor.fetchone()
            after = {
                "public_id": public_id.value,
                "semina_id": command.semina_id.value,
                "traceability_code": traceability.value,
                "quantity": str(command.quantity.value),
                "uom": UnitOfMeasure.SET.value,
                "effective_at": command.effective_at.isoformat(),
                "recorded_at": recorded_at.isoformat(),
                "notes": command.notes,
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'RACCOLTA',%s,'INSERT',%s,NULL,%s,%s,%s)""",
                (recorded_at, command.authority.actor.value, public_id.value,
                 command.authority.reason, Jsonb(after), command.authority.correlation_id,
                 json.dumps({"boundary": "raccolta-recording-v1",
                             "idempotency_key": command.authority.idempotency_key},
                            sort_keys=True)),
            )
            cursor.execute(
                """UPDATE tpo.raccolta_recording_requests
                   SET raccolta_id=%s,result_public_id=%s,outcome='COMMITTED'
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (raccolta_pk, public_id.value, reservation, command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise RaccoltaReconciliationRequiredError("Reservation RACCOLTA non aggiornabile.")
            cursor.execute(
                """UPDATE tpo.id_sequences SET next_value=%s,version=version+1,
                   updated_at=%s,updated_by=%s WHERE sequence_name=%s
                   AND identifier_type=%s AND prefix=%s AND next_value=%s AND version=%s""",
                (sequence[3] + 1, recorded_at, command.authority.actor.value,
                 RaccoltaId.sequence_name, RaccoltaId.__name__, RaccoltaId.prefix,
                 sequence[3], sequence[4]),
            )
            if cursor.rowcount != 1:
                raise RaccoltaIdentityUnavailableError("Conflitto contatore RACCOLTA_ID.")
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = RecordRaccoltaResult(
                public_id, command.semina_id, traceability, command.quantity,
                command.effective_at, recorded_at, "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise RaccoltaCommitOutcomeUncertainError(
                    "Esito commit RACCOLTA da riconciliare."
                ) from exc
            committed = True
            return result
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise RaccoltaCommitRolledBackError(
                "Registrazione RACCOLTA fallita con rollback certo."
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
    def _reserve_or_replay(cursor: Any, command: RecordRaccolta):
        cursor.execute(
            """INSERT INTO tpo.raccolta_recording_requests
               (operation_scope,idempotency_key,canonical_payload_hash,raccolta_id,
                result_public_id,outcome,recorded_at,created_by)
               VALUES (%s,%s,%s,NULL,NULL,'RESERVED',CURRENT_TIMESTAMP,%s)
               ON CONFLICT (operation_scope,idempotency_key) DO NOTHING
               RETURNING id""",
            (SCOPE, command.authority.idempotency_key, command.canonical_payload_hash,
             command.authority.actor.value),
        )
        row = cursor.fetchone()
        if row:
            return row[0], None
        cursor.execute(
            """SELECT q.canonical_payload_hash,q.outcome,r.public_id,s.public_id,
                      s.codice_tracciabilita,r.quantita,r.unita_misura,
                      r.data_raccolta,r.created_at
               FROM tpo.raccolta_recording_requests q
               LEFT JOIN tpo.raccolte r ON r.id=q.raccolta_id
               LEFT JOIN tpo.semine s ON s.id=r.semina_id
               WHERE q.operation_scope=%s AND q.idempotency_key=%s FOR UPDATE OF q""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if not row:
            raise RaccoltaReconciliationRequiredError("Reservation concorrente non leggibile.")
        if row[0] != command.canonical_payload_hash:
            raise RaccoltaIdempotencyConflictError(
                "Stessa idempotency key RACCOLTA con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise RaccoltaReconciliationRequiredError("Reservation priva di RACCOLTA committed.")
        try:
            return None, RecordRaccoltaResult(
                RaccoltaId(row[2]), SeminaId(row[3]), SeminaTraceabilityCode(row[4]),
                Quantity(row[5], UnitOfMeasure(row[6])), row[7], row[8],
                "COMPATIBLE_REPLAY",
            )
        except Exception as exc:
            raise RaccoltaPersistenceInvariantError("Risultato RACCOLTA persistito invalido.") from exc

    @staticmethod
    def _lock_semina(cursor: Any, command: RecordRaccolta):
        cursor.execute(
            """SELECT id,public_id,stato,codice_tracciabilita,version
               FROM tpo.semine WHERE public_id=%s FOR UPDATE""",
            (command.semina_id.value,),
        )
        row = cursor.fetchone()
        if not row:
            raise RaccoltaSeminaNotFoundError("SEMINA inesistente.")
        return row

    @staticmethod
    def _allocate(cursor: Any):
        cursor.execute(
            """SELECT sequence_name,identifier_type,prefix,next_value,version
               FROM tpo.id_sequences WHERE sequence_name=%s FOR UPDATE""",
            (RaccoltaId.sequence_name,),
        )
        row = cursor.fetchone()
        if not row or row[1] != RaccoltaId.__name__ or row[2] != RaccoltaId.prefix:
            raise RaccoltaIdentityUnavailableError("RACCOLTA_ID assente o incompatibile.")
        try:
            return RaccoltaId(f"{row[2]}-{row[3]:06d}"), row
        except Exception as exc:
            raise RaccoltaIdentityUnavailableError("RACCOLTA_ID malformata.") from exc

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if name == "uq_raccolta_recording_request_key":
            return RaccoltaReconciliationRequiredError("Collisione idempotency da riconciliare.")
        if name in {"raccolte_public_id_key", "ck_raccolte_public_id_format"}:
            return RaccoltaIdentityUnavailableError("Collisione RAC identity.")
        if name.startswith("ck_raccolte_"):
            return RaccoltaPersistenceInvariantError("Vincolo RACCOLTA non soddisfatto.")
        return RaccoltaCommitRolledBackError("Vincolo RACCOLTA non soddisfatto.")
