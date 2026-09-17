"""Writer PostgreSQL atomico PROGRAMMA_FORNITURA Sospensione/Riattivazione V1."""
from __future__ import annotations

from typing import Any

import psycopg

from ...application.programma_fornitura_sospensione.errors import (
    ProgrammaFornituraClienteGiaAttivoError, ProgrammaFornituraCommitOutcomeUncertainError,
    ProgrammaFornituraCommitRolledBackError, ProgrammaFornituraIdempotencyConflictError,
    ProgrammaFornituraIdentityUnavailableError, ProgrammaFornituraNotFoundError,
    ProgrammaFornituraPersistenceInvariantError, ProgrammaFornituraReconciliationRequiredError,
    ProgrammaFornituraStateIneligibleError, ProgrammaFornituraTimestampRegressionError,
    ProgrammaFornituraVersionConflictError,
)
from ...application.programma_fornitura_sospensione.models import (
    RiattivaProgrammaFornitura, RiattivaProgrammaFornituraResult, SospendiProgrammaFornitura,
    SospendiProgrammaFornituraResult,
)
from ...domain.identifiers import ProgrammaFornituraId
from .connection import PostgreSQLConnectionFactory

SCOPE_SOSPENDI = "PROGRAMMA_FORNITURA_SOSPENDI_V1"
SCOPE_RIATTIVA = "PROGRAMMA_FORNITURA_RIATTIVA_V1"


class PostgreSQLProgrammaFornituraSospensioneWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def sospendi(self, command: SospendiProgrammaFornitura) -> SospendiProgrammaFornituraResult:
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            reservation, recorded_at, replay = self._reserve_or_replay_sospendi(cursor, command)
            if replay is not None:
                connection.rollback()
                return replay
            if reservation is None or recorded_at is None:
                raise ProgrammaFornituraReconciliationRequiredError(
                    "Reservation PROGRAMMA_FORNITURA SOSPENDI non riconciliabile."
                )
            current = self._lock_current_version(cursor, command.programma_id)
            if current[4] != command.expected_numero_versione:
                raise ProgrammaFornituraVersionConflictError("Versione PROGRAMMA_FORNITURA non corrente.")
            if current[5] != "ATTIVO":
                raise ProgrammaFornituraStateIneligibleError(
                    "PROGRAMMA_FORNITURA non ATTIVO: sospensione non ammessa."
                )
            if command.effective_at <= current[10]:
                raise ProgrammaFornituraTimestampRegressionError(
                    "effective_at non successivo all'inizio della versione corrente."
                )
            new_version = self._close_and_insert_version(
                cursor, current, command.effective_at, "SOSPESO", command.authority.actor.value,
            )
            cursor.execute(
                """UPDATE tpo.programmi_fornitura SET data_ripresa_prevista=%s WHERE id=%s""",
                (command.data_ripresa_prevista, current[0]),
            )
            before = {"stato": "ATTIVO", "numero_versione": current[4]}
            after = {
                "stato": "SOSPESO", "numero_versione": new_version,
                "data_ripresa_prevista": (
                    command.data_ripresa_prevista.isoformat()
                    if command.data_ripresa_prevista else None
                ),
                "effective_at": command.effective_at.isoformat(),
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'PROGRAMMA_FORNITURA',%s,'STATE_TRANSITION',%s,%s,%s,%s,%s)""",
                (recorded_at, command.authority.actor.value, command.programma_id.value,
                 command.authority.reason, _jsonb(before), _jsonb(after),
                 command.authority.correlation_id,
                 _jsonb({"boundary": "programma-fornitura-sospendi-v1",
                         "idempotency_key": command.authority.idempotency_key})),
            )
            cursor.execute(
                """UPDATE tpo.programma_fornitura_sospendi_requests
                   SET outcome='COMMITTED',programma_fornitura_id=%s,result_numero_versione=%s,
                       result_data_ripresa_prevista=%s
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (current[0], new_version, command.data_ripresa_prevista, reservation,
                 command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise ProgrammaFornituraReconciliationRequiredError(
                    "Reservation PROGRAMMA_FORNITURA SOSPENDI non aggiornabile."
                )
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = SospendiProgrammaFornituraResult(
                command.programma_id, current[4], new_version, "ATTIVO", "SOSPESO",
                command.data_ripresa_prevista, command.effective_at, recorded_at, "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise ProgrammaFornituraCommitOutcomeUncertainError(
                    "Esito commit PROGRAMMA_FORNITURA SOSPENDI da riconciliare."
                ) from exc
            committed = True
            return result
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise ProgrammaFornituraCommitRolledBackError(
                "Sospensione PROGRAMMA_FORNITURA fallita con rollback certo."
            ) from exc
        finally:
            self._cleanup(connection, cursor, committed)

    def riattiva(self, command: RiattivaProgrammaFornitura) -> RiattivaProgrammaFornituraResult:
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            reservation, recorded_at, replay = self._reserve_or_replay_riattiva(cursor, command)
            if replay is not None:
                connection.rollback()
                return replay
            if reservation is None or recorded_at is None:
                raise ProgrammaFornituraReconciliationRequiredError(
                    "Reservation PROGRAMMA_FORNITURA RIATTIVA non riconciliabile."
                )
            current = self._lock_current_version(cursor, command.programma_id)
            if current[4] != command.expected_numero_versione:
                raise ProgrammaFornituraVersionConflictError("Versione PROGRAMMA_FORNITURA non corrente.")
            if current[5] != "SOSPESO":
                raise ProgrammaFornituraStateIneligibleError(
                    "PROGRAMMA_FORNITURA non SOSPESO: riattivazione non ammessa."
                )
            if command.effective_at <= current[10]:
                raise ProgrammaFornituraTimestampRegressionError(
                    "effective_at non successivo all'inizio della versione corrente."
                )
            new_version = self._close_and_insert_version(
                cursor, current, command.effective_at, "ATTIVO", command.authority.actor.value,
            )
            before = {"stato": "SOSPESO", "numero_versione": current[4]}
            after = {
                "stato": "ATTIVO", "numero_versione": new_version,
                "effective_at": command.effective_at.isoformat(),
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'PROGRAMMA_FORNITURA',%s,'STATE_TRANSITION',%s,%s,%s,%s,%s)""",
                (recorded_at, command.authority.actor.value, command.programma_id.value,
                 command.authority.reason, _jsonb(before), _jsonb(after),
                 command.authority.correlation_id,
                 _jsonb({"boundary": "programma-fornitura-riattiva-v1",
                         "idempotency_key": command.authority.idempotency_key})),
            )
            cursor.execute(
                """UPDATE tpo.programma_fornitura_riattiva_requests
                   SET outcome='COMMITTED',programma_fornitura_id=%s,result_numero_versione=%s
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (current[0], new_version, reservation, command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise ProgrammaFornituraReconciliationRequiredError(
                    "Reservation PROGRAMMA_FORNITURA RIATTIVA non aggiornabile."
                )
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = RiattivaProgrammaFornituraResult(
                command.programma_id, current[4], new_version, "SOSPESO", "ATTIVO",
                command.effective_at, recorded_at, "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise ProgrammaFornituraCommitOutcomeUncertainError(
                    "Esito commit PROGRAMMA_FORNITURA RIATTIVA da riconciliare."
                ) from exc
            committed = True
            return result
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise ProgrammaFornituraCommitRolledBackError(
                "Riattivazione PROGRAMMA_FORNITURA fallita con rollback certo."
            ) from exc
        finally:
            self._cleanup(connection, cursor, committed)

    # -- shared helpers ---------------------------------------------------

    @staticmethod
    def _lock_current_version(cursor: Any, programma_id: ProgrammaFornituraId):
        cursor.execute(
            """SELECT p.id,p.cliente_id,p.public_id,pv.id,pv.numero_versione,pv.stato,
                      pv.data_inizio,pv.data_fine,pv.orario_generazione,
                      pv.finestra_operativa_giorni,pv.valida_dal
               FROM tpo.programmi_fornitura p
               JOIN tpo.programmi_fornitura_versioni pv
                 ON pv.programma_fornitura_id=p.id
               WHERE p.public_id=%s AND pv.valida_al IS NULL AND pv.voided_at IS NULL
               FOR UPDATE OF p,pv""",
            (programma_id.value,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ProgrammaFornituraNotFoundError("PROGRAMMA_FORNITURA inesistente o privo di versione corrente.")
        return row

    @staticmethod
    def _close_and_insert_version(cursor: Any, current: Any, effective_at: Any,
                                   target_stato: str, actor: str) -> int:
        (program_pk, cliente_id, _public_id, old_version_pk, numero_versione, _stato,
         data_inizio, data_fine, orario_generazione, finestra_operativa_giorni, _valida_dal) = current
        cursor.execute(
            """UPDATE tpo.programmi_fornitura_versioni SET valida_al=%s
               WHERE id=%s AND valida_al IS NULL""",
            (effective_at, old_version_pk),
        )
        if cursor.rowcount != 1:
            raise ProgrammaFornituraReconciliationRequiredError(
                "Conflitto concorrente sulla versione corrente PROGRAMMA_FORNITURA."
            )
        new_version = numero_versione + 1
        cursor.execute(
            """INSERT INTO tpo.programmi_fornitura_versioni
               (programma_fornitura_id,cliente_id,numero_versione,stato,data_inizio,
                data_fine,orario_generazione,finestra_operativa_giorni,valida_dal,
                valida_al,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s) RETURNING id""",
            (program_pk, cliente_id, new_version, target_stato, data_inizio, data_fine,
             orario_generazione, finestra_operativa_giorni, effective_at, actor),
        )
        new_version_pk = cursor.fetchone()[0]
        cursor.execute(
            """SELECT id,posizione,varieta_id,quantita,unita_misura,tipo_ricorrenza,
                      intervallo_giorni
               FROM tpo.righe_programma_fornitura WHERE programma_versione_id=%s
               ORDER BY posizione""",
            (old_version_pk,),
        )
        righe = cursor.fetchall()
        for (old_riga_id, posizione, varieta_id, quantita, unita_misura, tipo_ricorrenza,
             intervallo_giorni) in righe:
            cursor.execute(
                """INSERT INTO tpo.righe_programma_fornitura
                   (programma_versione_id,posizione,varieta_id,quantita,unita_misura,
                    tipo_ricorrenza,intervallo_giorni)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (new_version_pk, posizione, varieta_id, quantita, unita_misura,
                 tipo_ricorrenza, intervallo_giorni),
            )
            new_riga_id = cursor.fetchone()[0]
            cursor.execute(
                "SELECT giorno_iso FROM tpo.righe_programma_giorni WHERE riga_programma_id=%s",
                (old_riga_id,),
            )
            for (giorno_iso,) in cursor.fetchall():
                cursor.execute(
                    "INSERT INTO tpo.righe_programma_giorni(riga_programma_id,giorno_iso) VALUES (%s,%s)",
                    (new_riga_id, giorno_iso),
                )
        return new_version

    @staticmethod
    def _reserve_or_replay_sospendi(cursor: Any, command: SospendiProgrammaFornitura):
        cursor.execute(
            """INSERT INTO tpo.programma_fornitura_sospendi_requests
               (operation_scope,idempotency_key,canonical_payload_hash,outcome,recorded_at,
                created_by)
               VALUES (%s,%s,%s,'RESERVED',CURRENT_TIMESTAMP,%s)
               ON CONFLICT (operation_scope,idempotency_key) DO NOTHING
               RETURNING id,recorded_at""",
            (SCOPE_SOSPENDI, command.authority.idempotency_key, command.canonical_payload_hash,
             command.authority.actor.value),
        )
        row = cursor.fetchone()
        if row:
            return row[0], row[1], None
        cursor.execute(
            """SELECT r.canonical_payload_hash,r.outcome,pv.numero_versione,pv.stato,
                      pv.valida_dal,r.result_data_ripresa_prevista,r.recorded_at
               FROM tpo.programma_fornitura_sospendi_requests r
               LEFT JOIN tpo.programmi_fornitura_versioni pv
                 ON pv.programma_fornitura_id=r.programma_fornitura_id
                AND pv.numero_versione=r.result_numero_versione
               WHERE r.operation_scope=%s AND r.idempotency_key=%s FOR UPDATE OF r""",
            (SCOPE_SOSPENDI, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if not row:
            raise ProgrammaFornituraReconciliationRequiredError("Reservation concorrente non leggibile.")
        if row[0] != command.canonical_payload_hash:
            raise ProgrammaFornituraIdempotencyConflictError(
                "Stessa idempotency key PROGRAMMA_FORNITURA SOSPENDI con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise ProgrammaFornituraReconciliationRequiredError(
                "Reservation priva di transizione SOSPENDI committed."
            )
        try:
            return None, None, SospendiProgrammaFornituraResult(
                command.programma_id, row[2] - 1, row[2], "ATTIVO", row[3], row[5], row[4],
                row[6], "COMPATIBLE_REPLAY",
            )
        except Exception as exc:
            raise ProgrammaFornituraPersistenceInvariantError(
                "Risultato PROGRAMMA_FORNITURA SOSPENDI persistito invalido."
            ) from exc

    @staticmethod
    def _reserve_or_replay_riattiva(cursor: Any, command: RiattivaProgrammaFornitura):
        cursor.execute(
            """INSERT INTO tpo.programma_fornitura_riattiva_requests
               (operation_scope,idempotency_key,canonical_payload_hash,outcome,recorded_at,
                created_by)
               VALUES (%s,%s,%s,'RESERVED',CURRENT_TIMESTAMP,%s)
               ON CONFLICT (operation_scope,idempotency_key) DO NOTHING
               RETURNING id,recorded_at""",
            (SCOPE_RIATTIVA, command.authority.idempotency_key, command.canonical_payload_hash,
             command.authority.actor.value),
        )
        row = cursor.fetchone()
        if row:
            return row[0], row[1], None
        cursor.execute(
            """SELECT r.canonical_payload_hash,r.outcome,pv.numero_versione,pv.stato,pv.valida_dal,
                      r.recorded_at
               FROM tpo.programma_fornitura_riattiva_requests r
               LEFT JOIN tpo.programmi_fornitura_versioni pv
                 ON pv.programma_fornitura_id=r.programma_fornitura_id
                AND pv.numero_versione=r.result_numero_versione
               WHERE r.operation_scope=%s AND r.idempotency_key=%s FOR UPDATE OF r""",
            (SCOPE_RIATTIVA, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if not row:
            raise ProgrammaFornituraReconciliationRequiredError("Reservation concorrente non leggibile.")
        if row[0] != command.canonical_payload_hash:
            raise ProgrammaFornituraIdempotencyConflictError(
                "Stessa idempotency key PROGRAMMA_FORNITURA RIATTIVA con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise ProgrammaFornituraReconciliationRequiredError(
                "Reservation priva di transizione RIATTIVA committed."
            )
        try:
            return None, None, RiattivaProgrammaFornituraResult(
                command.programma_id, row[2] - 1, row[2], "SOSPESO", row[3], row[4], row[5],
                "COMPATIBLE_REPLAY",
            )
        except Exception as exc:
            raise ProgrammaFornituraPersistenceInvariantError(
                "Risultato PROGRAMMA_FORNITURA RIATTIVA persistito invalido."
            ) from exc

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if name in {"uq_pf_sospendi_request_key", "uq_pf_riattiva_request_key"}:
            return ProgrammaFornituraReconciliationRequiredError("Collisione idempotency da riconciliare.")
        if name == "uq_programmi_fornitura_versioni_cliente_attivo":
            return ProgrammaFornituraClienteGiaAttivoError(
                "Il CLIENTE possiede gia' un altro PROGRAMMA_FORNITURA ATTIVO."
            )
        if name == "uq_programmi_fornitura_versioni_corrente":
            return ProgrammaFornituraReconciliationRequiredError(
                "Conflitto concorrente sulla versione corrente PROGRAMMA_FORNITURA."
            )
        if name.startswith("ck_programmi_fornitura_versioni") or name.startswith("uq_programmi_fornitura_versioni"):
            return ProgrammaFornituraPersistenceInvariantError("Vincolo PROGRAMMA_FORNITURA non soddisfatto.")
        return ProgrammaFornituraCommitRolledBackError("Vincolo PROGRAMMA_FORNITURA non soddisfatto.")

    @staticmethod
    def _cleanup(connection: Any, cursor: Any, committed: bool) -> None:
        if not committed:
            try: connection.rollback()
            except Exception: pass
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        try: connection.close()
        except Exception: pass


def _jsonb(payload: dict) -> Any:
    from psycopg.types.json import Jsonb
    return Jsonb(payload)
