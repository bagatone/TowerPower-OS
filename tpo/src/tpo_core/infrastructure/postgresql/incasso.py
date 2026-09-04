"""Writer PostgreSQL atomico per Incasso Recording Boundary V1 e Incasso Correzione V1."""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.incasso.errors import (
    IncassoCommitOutcomeUncertainError, IncassoCommitRolledBackError,
    IncassoCorrectionFatturaMismatchError, IncassoFatturaNotFoundError,
    IncassoIdempotencyConflictError, IncassoIdentityUnavailableError,
    IncassoOriginalIsCorrectionError, IncassoOriginalNotFoundError,
    IncassoPersistenceInvariantError, IncassoReconciliationRequiredError,
)
from ...application.incasso.models import (
    CorreggiIncasso, CorreggiIncassoResult, RegistraIncasso, RegistraIncassoResult,
)
from ...domain.identifiers import IncassoId, NumeroFattura
from ...domain.states import MetodoPagamento
from .connection import PostgreSQLConnectionFactory

SCOPE = "INCASSO_RECORDING_V1"
SCOPE_CORREZIONE = "INCASSO_CORREZIONE_V1"


class PostgreSQLIncassoWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def record(self, command: RegistraIncasso) -> RegistraIncassoResult:
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
                raise IncassoReconciliationRequiredError("Reservation INCASSO non riconciliabile.")
            cursor.execute(
                "SELECT numero_fattura FROM tpo.fatture WHERE numero_fattura=%s",
                (command.fattura_numero.value,),
            )
            if cursor.fetchone() is None:
                raise IncassoFatturaNotFoundError("FATTURA inesistente.")
            public_id, sequence = self._allocate(cursor)
            cursor.execute(
                """INSERT INTO tpo.incassi
                   (public_id,fattura_numero,importo,data_incasso,metodo,note,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id,created_at""",
                (public_id.value, command.fattura_numero.value, command.importo,
                 command.data_incasso, command.metodo.value, command.note,
                 command.authority.actor.value),
            )
            incasso_pk, recorded_at = cursor.fetchone()
            after = {
                "public_id": public_id.value,
                "fattura_numero": command.fattura_numero.value,
                "importo": str(command.importo),
                "data_incasso": command.data_incasso.isoformat(),
                "metodo": command.metodo.value,
                "recorded_at": recorded_at.isoformat(),
                "note": command.note,
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'INCASSO',%s,'INSERT',%s,NULL,%s,%s,%s)""",
                (recorded_at, command.authority.actor.value, public_id.value,
                 command.authority.reason, Jsonb(after), command.authority.correlation_id,
                 json.dumps({"boundary": "incasso-recording-v1",
                             "idempotency_key": command.authority.idempotency_key},
                            sort_keys=True)),
            )
            cursor.execute(
                """UPDATE tpo.incasso_recording_requests
                   SET incasso_id=%s,result_public_id=%s,outcome='COMMITTED'
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (incasso_pk, public_id.value, reservation, command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise IncassoReconciliationRequiredError("Reservation INCASSO non aggiornabile.")
            cursor.execute(
                """UPDATE tpo.id_sequences SET next_value=%s,version=version+1,
                   updated_at=%s,updated_by=%s WHERE sequence_name=%s
                   AND identifier_type=%s AND prefix=%s AND next_value=%s AND version=%s""",
                (sequence[3] + 1, recorded_at, command.authority.actor.value,
                 IncassoId.sequence_name, IncassoId.__name__, IncassoId.prefix,
                 sequence[3], sequence[4]),
            )
            if cursor.rowcount != 1:
                raise IncassoIdentityUnavailableError("Conflitto contatore INCASSO_ID.")
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = RegistraIncassoResult(
                public_id, command.fattura_numero, command.importo, command.data_incasso,
                command.metodo, recorded_at, "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise IncassoCommitOutcomeUncertainError(
                    "Esito commit INCASSO da riconciliare."
                ) from exc
            committed = True
            return result
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise IncassoCommitRolledBackError(
                "Registrazione INCASSO fallita con rollback certo."
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

    def correct(self, command: CorreggiIncasso) -> CorreggiIncassoResult:
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
                raise IncassoReconciliationRequiredError(
                    "Reservation INCASSO CORREZIONE non riconciliabile."
                )
            original = self._lock_original(cursor, command)
            if command.fattura_numero.value != original[1]:
                raise IncassoCorrectionFatturaMismatchError(
                    "La rettifica deve riferirsi alla stessa FATTURA dell'evento originario."
                )
            public_id, sequence = self._allocate(cursor)
            cursor.execute(
                """INSERT INTO tpo.incassi
                   (public_id,fattura_numero,importo,data_incasso,metodo,
                    rettifica_incasso_id,note,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id,created_at""",
                (public_id.value, command.fattura_numero.value, command.importo,
                 command.data_incasso, command.metodo.value, original[0], command.note,
                 command.authority.actor.value),
            )
            incasso_pk, recorded_at = cursor.fetchone()
            before = {"original_public_id": command.original_incasso_id.value}
            after = {
                "public_id": public_id.value,
                "original_public_id": command.original_incasso_id.value,
                "fattura_numero": command.fattura_numero.value,
                "importo": str(command.importo),
                "data_incasso": command.data_incasso.isoformat(),
                "metodo": command.metodo.value,
                "recorded_at": recorded_at.isoformat(),
                "note": command.note,
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'INCASSO',%s,'CORRECTION',%s,%s,%s,%s,%s)""",
                (recorded_at, command.authority.actor.value, public_id.value,
                 command.authority.reason, Jsonb(before), Jsonb(after),
                 command.authority.correlation_id,
                 json.dumps({"boundary": "incasso-correzione-v1",
                             "idempotency_key": command.authority.idempotency_key},
                            sort_keys=True)),
            )
            cursor.execute(
                """UPDATE tpo.incasso_correzione_requests
                   SET incasso_id=%s,result_public_id=%s,outcome='COMMITTED'
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (incasso_pk, public_id.value, reservation, command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise IncassoReconciliationRequiredError(
                    "Reservation INCASSO CORREZIONE non aggiornabile."
                )
            cursor.execute(
                """UPDATE tpo.id_sequences SET next_value=%s,version=version+1,
                   updated_at=%s,updated_by=%s WHERE sequence_name=%s
                   AND identifier_type=%s AND prefix=%s AND next_value=%s AND version=%s""",
                (sequence[3] + 1, recorded_at, command.authority.actor.value,
                 IncassoId.sequence_name, IncassoId.__name__, IncassoId.prefix,
                 sequence[3], sequence[4]),
            )
            if cursor.rowcount != 1:
                raise IncassoIdentityUnavailableError("Conflitto contatore INCASSO_ID.")
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = CorreggiIncassoResult(
                public_id, command.original_incasso_id, command.fattura_numero,
                command.importo, command.data_incasso, command.metodo, recorded_at,
                "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise IncassoCommitOutcomeUncertainError(
                    "Esito commit INCASSO CORREZIONE da riconciliare."
                ) from exc
            committed = True
            return result
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise IncassoCommitRolledBackError(
                "Correzione INCASSO fallita con rollback certo."
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
    def _reserve_or_replay_correction(cursor: Any, command: CorreggiIncasso):
        cursor.execute(
            """INSERT INTO tpo.incasso_correzione_requests
               (operation_scope,idempotency_key,canonical_payload_hash,incasso_id,
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
            """SELECT q.canonical_payload_hash,q.outcome,i.public_id,orig.public_id,
                      i.fattura_numero,i.importo,i.data_incasso,i.metodo,i.created_at
               FROM tpo.incasso_correzione_requests q
               LEFT JOIN tpo.incassi i ON i.id=q.incasso_id
               LEFT JOIN tpo.incassi orig ON orig.id=i.rettifica_incasso_id
               WHERE q.operation_scope=%s AND q.idempotency_key=%s FOR UPDATE OF q""",
            (SCOPE_CORREZIONE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if not row:
            raise IncassoReconciliationRequiredError("Reservation concorrente non leggibile.")
        if row[0] != command.canonical_payload_hash:
            raise IncassoIdempotencyConflictError(
                "Stessa idempotency key INCASSO CORREZIONE con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise IncassoReconciliationRequiredError(
                "Reservation priva di INCASSO CORREZIONE committed."
            )
        try:
            return None, CorreggiIncassoResult(
                IncassoId(row[2]), IncassoId(row[3]), NumeroFattura(row[4]), Decimal(row[5]),
                row[6], MetodoPagamento(row[7]), row[8], "COMPATIBLE_REPLAY",
            )
        except Exception as exc:
            raise IncassoPersistenceInvariantError(
                "Risultato INCASSO CORREZIONE persistito invalido."
            ) from exc

    @staticmethod
    def _lock_original(cursor: Any, command: CorreggiIncasso):
        cursor.execute(
            """SELECT id,fattura_numero,importo,rettifica_incasso_id
               FROM tpo.incassi WHERE public_id=%s FOR UPDATE""",
            (command.original_incasso_id.value,),
        )
        row = cursor.fetchone()
        if not row:
            raise IncassoOriginalNotFoundError("INCASSO originale inesistente.")
        if row[3] is not None:
            raise IncassoOriginalIsCorrectionError(
                "L'evento referenziato è già una rettifica; niente rettifica-di-rettifica "
                "concatenata."
            )
        return row

    @staticmethod
    def _reserve_or_replay(cursor: Any, command: RegistraIncasso):
        cursor.execute(
            """INSERT INTO tpo.incasso_recording_requests
               (operation_scope,idempotency_key,canonical_payload_hash,incasso_id,
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
            """SELECT q.canonical_payload_hash,q.outcome,i.public_id,i.fattura_numero,
                      i.importo,i.data_incasso,i.metodo,i.created_at
               FROM tpo.incasso_recording_requests q
               LEFT JOIN tpo.incassi i ON i.id=q.incasso_id
               WHERE q.operation_scope=%s AND q.idempotency_key=%s FOR UPDATE OF q""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if not row:
            raise IncassoReconciliationRequiredError("Reservation concorrente non leggibile.")
        if row[0] != command.canonical_payload_hash:
            raise IncassoIdempotencyConflictError(
                "Stessa idempotency key INCASSO con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise IncassoReconciliationRequiredError("Reservation priva di INCASSO committed.")
        try:
            return None, RegistraIncassoResult(
                IncassoId(row[2]), NumeroFattura(row[3]), Decimal(row[4]), row[5],
                MetodoPagamento(row[6]), row[7], "COMPATIBLE_REPLAY",
            )
        except Exception as exc:
            raise IncassoPersistenceInvariantError("Risultato INCASSO persistito invalido.") from exc

    @staticmethod
    def _allocate(cursor: Any):
        cursor.execute(
            """SELECT sequence_name,identifier_type,prefix,next_value,version
               FROM tpo.id_sequences WHERE sequence_name=%s FOR UPDATE""",
            (IncassoId.sequence_name,),
        )
        row = cursor.fetchone()
        if not row or row[1] != IncassoId.__name__ or row[2] != IncassoId.prefix:
            raise IncassoIdentityUnavailableError("INCASSO_ID assente o incompatibile.")
        try:
            return IncassoId(f"{row[2]}-{row[3]:06d}"), row
        except Exception as exc:
            raise IncassoIdentityUnavailableError("INCASSO_ID malformata.") from exc

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if name in {"uq_incasso_recording_request_key", "uq_incasso_correzione_request_key"}:
            return IncassoReconciliationRequiredError("Collisione idempotency da riconciliare.")
        if name in {"incassi_public_id_key", "ck_incassi_public_id_format"}:
            return IncassoIdentityUnavailableError("Collisione INC identity.")
        if (name.startswith("ck_incassi_") or name in
                {"fk_incassi_rettifica", "fk_incassi_fattura"}):
            return IncassoPersistenceInvariantError("Vincolo INCASSO non soddisfatto.")
        return IncassoCommitRolledBackError("Vincolo INCASSO non soddisfatto.")
