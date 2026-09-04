"""Writer PostgreSQL atomico per Uscita Recording Boundary V1 e Uscita Correzione V1."""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.uscita.errors import (
    UscitaCommitOutcomeUncertainError, UscitaCommitRolledBackError,
    UscitaIdempotencyConflictError, UscitaIdentityUnavailableError,
    UscitaOriginalIsCorrectionError, UscitaOriginalNotFoundError,
    UscitaPersistenceInvariantError, UscitaReconciliationRequiredError,
)
from ...application.uscita.models import (
    CorreggiUscita, CorreggiUscitaResult, RegistraUscita, RegistraUscitaResult,
)
from ...domain.identifiers import UscitaId
from ...domain.states import CategoriaUscita, MetodoPagamento
from .connection import PostgreSQLConnectionFactory

SCOPE = "USCITA_RECORDING_V1"
SCOPE_CORREZIONE = "USCITA_CORREZIONE_V1"


class PostgreSQLUscitaWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def record(self, command: RegistraUscita) -> RegistraUscitaResult:
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
                raise UscitaReconciliationRequiredError("Reservation USCITA non riconciliabile.")
            public_id, sequence = self._allocate(cursor)
            cursor.execute(
                """INSERT INTO tpo.uscite
                   (public_id,importo,data_uscita,categoria,beneficiario,metodo,note,
                    created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id,created_at""",
                (public_id.value, command.importo, command.data_uscita,
                 command.categoria.value, command.beneficiario, command.metodo.value,
                 command.note, command.authority.actor.value),
            )
            uscita_pk, recorded_at = cursor.fetchone()
            after = {
                "public_id": public_id.value,
                "importo": str(command.importo),
                "data_uscita": command.data_uscita.isoformat(),
                "categoria": command.categoria.value,
                "beneficiario": command.beneficiario,
                "metodo": command.metodo.value,
                "recorded_at": recorded_at.isoformat(),
                "note": command.note,
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'USCITA',%s,'INSERT',%s,NULL,%s,%s,%s)""",
                (recorded_at, command.authority.actor.value, public_id.value,
                 command.authority.reason, Jsonb(after), command.authority.correlation_id,
                 json.dumps({"boundary": "uscita-recording-v1",
                             "idempotency_key": command.authority.idempotency_key},
                            sort_keys=True)),
            )
            cursor.execute(
                """UPDATE tpo.uscita_recording_requests
                   SET uscita_id=%s,result_public_id=%s,outcome='COMMITTED'
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (uscita_pk, public_id.value, reservation, command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise UscitaReconciliationRequiredError("Reservation USCITA non aggiornabile.")
            cursor.execute(
                """UPDATE tpo.id_sequences SET next_value=%s,version=version+1,
                   updated_at=%s,updated_by=%s WHERE sequence_name=%s
                   AND identifier_type=%s AND prefix=%s AND next_value=%s AND version=%s""",
                (sequence[3] + 1, recorded_at, command.authority.actor.value,
                 UscitaId.sequence_name, UscitaId.__name__, UscitaId.prefix,
                 sequence[3], sequence[4]),
            )
            if cursor.rowcount != 1:
                raise UscitaIdentityUnavailableError("Conflitto contatore USCITA_ID.")
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = RegistraUscitaResult(
                public_id, command.importo, command.data_uscita, command.categoria,
                command.beneficiario, command.metodo, recorded_at, "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise UscitaCommitOutcomeUncertainError(
                    "Esito commit USCITA da riconciliare."
                ) from exc
            committed = True
            return result
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise UscitaCommitRolledBackError(
                "Registrazione USCITA fallita con rollback certo."
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

    def correct(self, command: CorreggiUscita) -> CorreggiUscitaResult:
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            reservation, replay = self._reserve_or_replay_correction(cursor, command)
            if replay is not None:
                connection.rollback()
                return replay
            if reservation is None:
                raise UscitaReconciliationRequiredError(
                    "Reservation USCITA CORREZIONE non riconciliabile."
                )
            original = self._lock_original(cursor, command)
            public_id, sequence = self._allocate(cursor)
            cursor.execute(
                """INSERT INTO tpo.uscite
                   (public_id,importo,data_uscita,categoria,beneficiario,metodo,
                    rettifica_uscita_id,note,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id,created_at""",
                (public_id.value, command.importo, command.data_uscita,
                 command.categoria.value, command.beneficiario, command.metodo.value,
                 original[0], command.note, command.authority.actor.value),
            )
            uscita_pk, recorded_at = cursor.fetchone()
            before = {"original_public_id": command.original_uscita_id.value}
            after = {
                "public_id": public_id.value,
                "original_public_id": command.original_uscita_id.value,
                "importo": str(command.importo),
                "data_uscita": command.data_uscita.isoformat(),
                "categoria": command.categoria.value,
                "beneficiario": command.beneficiario,
                "metodo": command.metodo.value,
                "recorded_at": recorded_at.isoformat(),
                "note": command.note,
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'USCITA',%s,'CORRECTION',%s,%s,%s,%s,%s)""",
                (recorded_at, command.authority.actor.value, public_id.value,
                 command.authority.reason, Jsonb(before), Jsonb(after),
                 command.authority.correlation_id,
                 json.dumps({"boundary": "uscita-correzione-v1",
                             "idempotency_key": command.authority.idempotency_key},
                            sort_keys=True)),
            )
            cursor.execute(
                """UPDATE tpo.uscita_correzione_requests
                   SET uscita_id=%s,result_public_id=%s,outcome='COMMITTED'
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (uscita_pk, public_id.value, reservation, command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise UscitaReconciliationRequiredError(
                    "Reservation USCITA CORREZIONE non aggiornabile."
                )
            cursor.execute(
                """UPDATE tpo.id_sequences SET next_value=%s,version=version+1,
                   updated_at=%s,updated_by=%s WHERE sequence_name=%s
                   AND identifier_type=%s AND prefix=%s AND next_value=%s AND version=%s""",
                (sequence[3] + 1, recorded_at, command.authority.actor.value,
                 UscitaId.sequence_name, UscitaId.__name__, UscitaId.prefix,
                 sequence[3], sequence[4]),
            )
            if cursor.rowcount != 1:
                raise UscitaIdentityUnavailableError("Conflitto contatore USCITA_ID.")
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = CorreggiUscitaResult(
                public_id, command.original_uscita_id, command.importo, command.data_uscita,
                command.categoria, command.beneficiario, command.metodo, recorded_at,
                "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise UscitaCommitOutcomeUncertainError(
                    "Esito commit USCITA CORREZIONE da riconciliare."
                ) from exc
            committed = True
            return result
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise UscitaCommitRolledBackError(
                "Correzione USCITA fallita con rollback certo."
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
    def _reserve_or_replay_correction(cursor: Any, command: CorreggiUscita):
        cursor.execute(
            """INSERT INTO tpo.uscita_correzione_requests
               (operation_scope,idempotency_key,canonical_payload_hash,uscita_id,
                result_public_id,outcome,recorded_at,created_by)
               VALUES (%s,%s,%s,NULL,NULL,'RESERVED',CURRENT_TIMESTAMP,%s)
               ON CONFLICT (operation_scope,idempotency_key) DO NOTHING
               RETURNING id""",
            (SCOPE_CORREZIONE, command.authority.idempotency_key,
             command.canonical_payload_hash, command.authority.actor.value),
        )
        row = cursor.fetchone()
        if row:
            return row[0], None
        cursor.execute(
            """SELECT q.canonical_payload_hash,q.outcome,u.public_id,orig.public_id,
                      u.importo,u.data_uscita,u.categoria,u.beneficiario,u.metodo,
                      u.created_at
               FROM tpo.uscita_correzione_requests q
               LEFT JOIN tpo.uscite u ON u.id=q.uscita_id
               LEFT JOIN tpo.uscite orig ON orig.id=u.rettifica_uscita_id
               WHERE q.operation_scope=%s AND q.idempotency_key=%s FOR UPDATE OF q""",
            (SCOPE_CORREZIONE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if not row:
            raise UscitaReconciliationRequiredError("Reservation concorrente non leggibile.")
        if row[0] != command.canonical_payload_hash:
            raise UscitaIdempotencyConflictError(
                "Stessa idempotency key USCITA CORREZIONE con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise UscitaReconciliationRequiredError(
                "Reservation priva di USCITA CORREZIONE committed."
            )
        try:
            return None, CorreggiUscitaResult(
                UscitaId(row[2]), UscitaId(row[3]), Decimal(row[4]), row[5],
                CategoriaUscita(row[6]), row[7], MetodoPagamento(row[8]), row[9],
                "COMPATIBLE_REPLAY",
            )
        except Exception as exc:
            raise UscitaPersistenceInvariantError(
                "Risultato USCITA CORREZIONE persistito invalido."
            ) from exc

    @staticmethod
    def _lock_original(cursor: Any, command: CorreggiUscita):
        cursor.execute(
            """SELECT id,importo,rettifica_uscita_id
               FROM tpo.uscite WHERE public_id=%s FOR UPDATE""",
            (command.original_uscita_id.value,),
        )
        row = cursor.fetchone()
        if not row:
            raise UscitaOriginalNotFoundError("USCITA originale inesistente.")
        if row[2] is not None:
            raise UscitaOriginalIsCorrectionError(
                "L'evento referenziato è già una rettifica; niente rettifica-di-rettifica "
                "concatenata."
            )
        return row

    @staticmethod
    def _reserve_or_replay(cursor: Any, command: RegistraUscita):
        cursor.execute(
            """INSERT INTO tpo.uscita_recording_requests
               (operation_scope,idempotency_key,canonical_payload_hash,uscita_id,
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
            """SELECT q.canonical_payload_hash,q.outcome,u.public_id,u.importo,
                      u.data_uscita,u.categoria,u.beneficiario,u.metodo,u.created_at
               FROM tpo.uscita_recording_requests q
               LEFT JOIN tpo.uscite u ON u.id=q.uscita_id
               WHERE q.operation_scope=%s AND q.idempotency_key=%s FOR UPDATE OF q""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if not row:
            raise UscitaReconciliationRequiredError("Reservation concorrente non leggibile.")
        if row[0] != command.canonical_payload_hash:
            raise UscitaIdempotencyConflictError(
                "Stessa idempotency key USCITA con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise UscitaReconciliationRequiredError("Reservation priva di USCITA committed.")
        try:
            return None, RegistraUscitaResult(
                UscitaId(row[2]), Decimal(row[3]), row[4], CategoriaUscita(row[5]), row[6],
                MetodoPagamento(row[7]), row[8], "COMPATIBLE_REPLAY",
            )
        except Exception as exc:
            raise UscitaPersistenceInvariantError("Risultato USCITA persistito invalido.") from exc

    @staticmethod
    def _allocate(cursor: Any):
        cursor.execute(
            """SELECT sequence_name,identifier_type,prefix,next_value,version
               FROM tpo.id_sequences WHERE sequence_name=%s FOR UPDATE""",
            (UscitaId.sequence_name,),
        )
        row = cursor.fetchone()
        if not row or row[1] != UscitaId.__name__ or row[2] != UscitaId.prefix:
            raise UscitaIdentityUnavailableError("USCITA_ID assente o incompatibile.")
        try:
            return UscitaId(f"{row[2]}-{row[3]:06d}"), row
        except Exception as exc:
            raise UscitaIdentityUnavailableError("USCITA_ID malformata.") from exc

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if name in {"uq_uscita_recording_request_key", "uq_uscita_correzione_request_key"}:
            return UscitaReconciliationRequiredError("Collisione idempotency da riconciliare.")
        if name in {"uscite_public_id_key", "ck_uscite_public_id_format"}:
            return UscitaIdentityUnavailableError("Collisione USC identity.")
        if name.startswith("ck_uscite_") or name == "fk_uscite_rettifica":
            return UscitaPersistenceInvariantError("Vincolo USCITA non soddisfatto.")
        return UscitaCommitRolledBackError("Vincolo USCITA non soddisfatto.")
