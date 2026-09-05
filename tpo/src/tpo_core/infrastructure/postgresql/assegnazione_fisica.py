"""Writer PostgreSQL atomico per Assegnazione Fisica Boundary V1.

Autorità: docs/architecture/ASSEGNAZIONE_FISICA_AUTHORITY_FREEZE.md. Register
append-only (Fact-only): lega una RACCOLTA a una RIGA_ORDINE, con un
riferimento opzionale a una CONSEGNA (ASSEGNAZIONI.md). Nessun vincolo di
capienza/quantità (Owner Decision D-ASSEGNAZIONE_FISICA-capacity):
`raccolta_id`/`riga_ordine_id` sono verificati solo per esistenza, mai per
somma cumulata. Se `consegna_id` è fornito, deve essere collegata alla
stessa RIGA_ORDINE tramite `tpo.righe_consegna` (coerenza referenziale
minima, non un vincolo di business nuovo).
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.assegnazione_fisica.errors import (
    AssegnazioneFisicaCommitOutcomeUncertainError,
    AssegnazioneFisicaCommitRolledBackError,
    AssegnazioneFisicaConsegnaNotFoundError,
    AssegnazioneFisicaConsegnaRigaOrdineMismatchError,
    AssegnazioneFisicaIdempotencyConflictError,
    AssegnazioneFisicaIdentityUnavailableError,
    AssegnazioneFisicaPersistenceInvariantError,
    AssegnazioneFisicaRaccoltaNotFoundError,
    AssegnazioneFisicaReconciliationRequiredError,
    AssegnazioneFisicaRigaOrdineNotFoundError,
)
from ...application.assegnazione_fisica.models import (
    RegistraAssegnazioneFisica, RegistraAssegnazioneFisicaResult,
)
from ...domain.identifiers import (
    AssegnazioneFisicaId, ConsegnaId, RaccoltaId, RigaOrdineId,
)
from .connection import PostgreSQLConnectionFactory

SCOPE = "ASSEGNAZIONE_FISICA_V1"


class PostgreSQLAssegnazioneFisicaWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def registra(
        self, command: RegistraAssegnazioneFisica
    ) -> RegistraAssegnazioneFisicaResult:
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
                raise AssegnazioneFisicaReconciliationRequiredError(
                    "Reservation ASSEGNAZIONE_FISICA non riconciliabile."
                )
            raccolta_pk = self._lock_raccolta(cursor, command)
            riga_ordine_pk = self._lock_riga_ordine(cursor, command)
            consegna_pk = self._resolve_consegna(cursor, command, riga_ordine_pk)
            public_id, sequence = self._allocate(cursor)
            cursor.execute(
                """INSERT INTO tpo.assegnazioni_fisiche
                   (public_id,raccolta_id,riga_ordine_id,consegna_id,quantita_assegnata,
                    unita_misura,effective_at,motivo,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id,created_at""",
                (public_id.value, raccolta_pk, riga_ordine_pk, consegna_pk,
                 command.quantita_assegnata, command.unita_misura, command.effective_at,
                 command.motivo, command.authority.actor.value),
            )
            assegnazione_pk, recorded_at = cursor.fetchone()
            after = {
                "public_id": public_id.value,
                "raccolta_id": command.raccolta_id.value,
                "riga_ordine_id": command.riga_ordine_id.value,
                "consegna_id": (
                    command.consegna_id.value if command.consegna_id is not None else None
                ),
                "quantita_assegnata": str(command.quantita_assegnata),
                "uom": command.unita_misura,
                "effective_at": command.effective_at.isoformat(),
                "recorded_at": recorded_at.isoformat(),
                "motivo": command.motivo,
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'ASSEGNAZIONE_FISICA',%s,'INSERT',%s,NULL,%s,%s,%s)""",
                (recorded_at, command.authority.actor.value, public_id.value,
                 command.authority.reason, Jsonb(after), command.authority.correlation_id,
                 json.dumps({"boundary": "assegnazione-fisica-v1",
                             "idempotency_key": command.authority.idempotency_key},
                            sort_keys=True)),
            )
            cursor.execute(
                """UPDATE tpo.assegnazione_fisica_requests
                   SET assegnazione_fisica_id=%s,result_public_id=%s,outcome='COMMITTED'
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (assegnazione_pk, public_id.value, reservation, command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise AssegnazioneFisicaReconciliationRequiredError(
                    "Reservation ASSEGNAZIONE_FISICA non aggiornabile."
                )
            cursor.execute(
                """UPDATE tpo.id_sequences SET next_value=%s,version=version+1,
                   updated_at=%s,updated_by=%s WHERE sequence_name=%s
                   AND identifier_type=%s AND prefix=%s AND next_value=%s AND version=%s""",
                (sequence[3] + 1, recorded_at, command.authority.actor.value,
                 AssegnazioneFisicaId.sequence_name, AssegnazioneFisicaId.__name__,
                 AssegnazioneFisicaId.prefix, sequence[3], sequence[4]),
            )
            if cursor.rowcount != 1:
                raise AssegnazioneFisicaIdentityUnavailableError(
                    "Conflitto contatore ASSEGNAZIONE_FISICA_ID."
                )
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = RegistraAssegnazioneFisicaResult(
                public_id, command.raccolta_id, command.riga_ordine_id,
                command.quantita_assegnata, command.unita_misura, command.effective_at,
                recorded_at, "INSERTED", consegna_id=command.consegna_id,
            )
            try:
                connection.commit()
            except Exception as exc:
                raise AssegnazioneFisicaCommitOutcomeUncertainError(
                    "Esito commit ASSEGNAZIONE_FISICA da riconciliare."
                ) from exc
            committed = True
            return result
        except (AssegnazioneFisicaRaccoltaNotFoundError, AssegnazioneFisicaRigaOrdineNotFoundError,
                 AssegnazioneFisicaConsegnaNotFoundError,
                 AssegnazioneFisicaConsegnaRigaOrdineMismatchError,
                 AssegnazioneFisicaIdempotencyConflictError,
                 AssegnazioneFisicaReconciliationRequiredError,
                 AssegnazioneFisicaIdentityUnavailableError,
                 AssegnazioneFisicaCommitOutcomeUncertainError,
                 AssegnazioneFisicaPersistenceInvariantError):
            raise
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise AssegnazioneFisicaCommitRolledBackError(
                "ASSEGNAZIONE_FISICA fallita con rollback certo."
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
    def _reserve_or_replay(cursor: Any, command: RegistraAssegnazioneFisica):
        cursor.execute(
            """INSERT INTO tpo.assegnazione_fisica_requests
               (operation_scope,idempotency_key,canonical_payload_hash,
                assegnazione_fisica_id,result_public_id,outcome,recorded_at,created_by)
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
            """SELECT q.canonical_payload_hash,q.outcome,af.public_id,rac.public_id,
                      ro.public_id,con.public_id,af.quantita_assegnata,af.unita_misura,
                      af.effective_at,af.created_at
               FROM tpo.assegnazione_fisica_requests q
               LEFT JOIN tpo.assegnazioni_fisiche af ON af.id=q.assegnazione_fisica_id
               LEFT JOIN tpo.raccolte rac ON rac.id=af.raccolta_id
               LEFT JOIN tpo.righe_ordine ro ON ro.id=af.riga_ordine_id
               LEFT JOIN tpo.consegne con ON con.id=af.consegna_id
               WHERE q.operation_scope=%s AND q.idempotency_key=%s FOR UPDATE OF q""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if row is None:
            raise AssegnazioneFisicaReconciliationRequiredError(
                "Reservation ASSEGNAZIONE_FISICA concorrente non leggibile."
            )
        if row[0] != command.canonical_payload_hash:
            raise AssegnazioneFisicaIdempotencyConflictError(
                "Stessa idempotency key ASSEGNAZIONE_FISICA con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise AssegnazioneFisicaReconciliationRequiredError(
                "Reservation priva di ASSEGNAZIONE_FISICA committed."
            )
        try:
            return None, RegistraAssegnazioneFisicaResult(
                AssegnazioneFisicaId(row[2]), RaccoltaId(row[3]), RigaOrdineId(row[4]),
                Decimal(row[6]), row[7], row[8], row[9], "COMPATIBLE_REPLAY",
                consegna_id=ConsegnaId(row[5]) if row[5] is not None else None,
            )
        except Exception as exc:
            raise AssegnazioneFisicaPersistenceInvariantError(
                "Risultato ASSEGNAZIONE_FISICA persistito invalido."
            ) from exc

    @staticmethod
    def _lock_raccolta(cursor: Any, command: RegistraAssegnazioneFisica) -> int:
        cursor.execute(
            "SELECT id FROM tpo.raccolte WHERE public_id=%s FOR SHARE",
            (command.raccolta_id.value,),
        )
        row = cursor.fetchone()
        if row is None:
            raise AssegnazioneFisicaRaccoltaNotFoundError("RACCOLTA inesistente.")
        return row[0]

    @staticmethod
    def _lock_riga_ordine(cursor: Any, command: RegistraAssegnazioneFisica) -> int:
        cursor.execute(
            "SELECT id FROM tpo.righe_ordine WHERE public_id=%s FOR SHARE",
            (command.riga_ordine_id.value,),
        )
        row = cursor.fetchone()
        if row is None:
            raise AssegnazioneFisicaRigaOrdineNotFoundError("RIGA_ORDINE inesistente.")
        return row[0]

    @staticmethod
    def _resolve_consegna(
        cursor: Any, command: RegistraAssegnazioneFisica, riga_ordine_pk: int
    ) -> int | None:
        if command.consegna_id is None:
            return None
        cursor.execute(
            "SELECT id FROM tpo.consegne WHERE public_id=%s FOR SHARE",
            (command.consegna_id.value,),
        )
        row = cursor.fetchone()
        if row is None:
            raise AssegnazioneFisicaConsegnaNotFoundError("CONSEGNA inesistente.")
        consegna_pk = row[0]
        cursor.execute(
            "SELECT 1 FROM tpo.righe_consegna WHERE consegna_id=%s AND riga_ordine_id=%s",
            (consegna_pk, riga_ordine_pk),
        )
        if cursor.fetchone() is None:
            raise AssegnazioneFisicaConsegnaRigaOrdineMismatchError(
                "La CONSEGNA indicata non è collegata alla RIGA_ORDINE indicata."
            )
        return consegna_pk

    @staticmethod
    def _allocate(cursor: Any):
        cursor.execute(
            """SELECT sequence_name,identifier_type,prefix,next_value,version
               FROM tpo.id_sequences WHERE sequence_name=%s FOR UPDATE""",
            (AssegnazioneFisicaId.sequence_name,),
        )
        row = cursor.fetchone()
        if (not row or row[1] != AssegnazioneFisicaId.__name__
                or row[2] != AssegnazioneFisicaId.prefix):
            raise AssegnazioneFisicaIdentityUnavailableError(
                "ASSEGNAZIONE_FISICA_ID assente o incompatibile."
            )
        try:
            return AssegnazioneFisicaId(f"{row[2]}-{row[3]:06d}"), row
        except Exception as exc:
            raise AssegnazioneFisicaIdentityUnavailableError(
                "ASSEGNAZIONE_FISICA_ID malformata."
            ) from exc

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if name == "uq_assegnazione_fisica_request_key":
            return AssegnazioneFisicaReconciliationRequiredError(
                "Collisione idempotency da riconciliare."
            )
        if name in {"assegnazioni_fisiche_public_id_key", "ck_assegnazioni_fisiche_public_id_format"}:
            return AssegnazioneFisicaIdentityUnavailableError("Collisione ASF identity.")
        if name.startswith("ck_assegnazioni_fisiche_"):
            return AssegnazioneFisicaPersistenceInvariantError(
                "Vincolo ASSEGNAZIONE_FISICA non soddisfatto."
            )
        return AssegnazioneFisicaCommitRolledBackError(
            "Vincolo ASSEGNAZIONE_FISICA non soddisfatto."
        )
