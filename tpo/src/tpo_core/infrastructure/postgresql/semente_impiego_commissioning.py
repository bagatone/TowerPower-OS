"""Atomic PostgreSQL writer for Semente Impiego Commissioning V1."""

from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.semente_impiego_commissioning.errors import (
    ProtocolContextUnavailableError, SementeAuthorityAmbiguousError,
    SementeAuthorityInactiveError, SementeAuthorityNotFoundError,
    SementeImpiegoCommitRolledBackError, SementeImpiegoConcurrencyConflictError,
    SementeImpiegoDuplicateError, SementeImpiegoIdempotencyConflictError,
    SementeImpiegoReconciliationRequiredError,
)
from ...application.semente_impiego_commissioning.models import (
    CommissionSementeImpiego, CommissionSementeImpiegoResult,
)
from ...domain.states import SementeRaccomandazione
from .connection import PostgreSQLConnectionFactory

SCOPE = "SEMENTE_IMPIEGO_COMMISSIONING_V1"


class PostgreSQLSementeImpiegoCommissioningWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def commission(self, command: CommissionSementeImpiego) -> CommissionSementeImpiegoResult:
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
                raise SementeImpiegoReconciliationRequiredError(
                    "Reservation idempotency non riconciliabile."
                )
            semente_id = self._semente(cursor, command)
            context = self._context(cursor, command, semente_id)
            cultivar_uso_id = context[0]
            self._assert_not_duplicate(cursor, semente_id, cultivar_uso_id)
            cursor.execute(
                """INSERT INTO tpo.semente_impieghi
                   (semente_id,cultivar_uso_id,raccomandazione,rating,motivazione,
                    ultima_revisione,created_by,updated_at,updated_by,version)
                   VALUES (%s,%s,%s,%s,%s,CURRENT_DATE,%s,CURRENT_TIMESTAMP,%s,0)
                   RETURNING id,created_at,ultima_revisione""",
                (semente_id, cultivar_uso_id, command.raccomandazione.value, command.rating,
                 command.motivazione, command.authority.actor.value, command.authority.actor.value),
            )
            impiego_pk, recorded_at, ultima_revisione = cursor.fetchone()
            cursor.execute(
                """UPDATE tpo.semente_impiego_commissioning_requests
                   SET semente_impiego_id=%s,outcome='COMMITTED',recorded_at=%s
                   WHERE id=%s AND operation_scope=%s
                     AND canonical_payload_hash=%s AND outcome='RESERVED'
                     AND semente_impiego_id IS NULL""",
                (impiego_pk, recorded_at, reservation_id, SCOPE,
                 command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise SementeImpiegoConcurrencyConflictError(
                    "Reservation idempotency non aggiornabile."
                )
            self._audit(cursor, impiego_pk, command, context, recorded_at)
            result = _result(impiego_pk, command, context, ultima_revisione, recorded_at, "INSERTED")
            try:
                connection.commit()
            except Exception as exc:
                raise SementeImpiegoReconciliationRequiredError(
                    "Esito commit SEMENTE_IMPIEGO da riconciliare."
                ) from exc
            committed = True
            return result
        except (SementeAuthorityNotFoundError, SementeAuthorityInactiveError,
                SementeAuthorityAmbiguousError, ProtocolContextUnavailableError,
                SementeImpiegoDuplicateError, SementeImpiegoIdempotencyConflictError,
                SementeImpiegoConcurrencyConflictError, SementeImpiegoReconciliationRequiredError):
            raise
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise SementeImpiegoCommitRolledBackError(
                "Commissioning SEMENTE_IMPIEGO fallito con rollback certo."
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
        cursor: Any, command: CommissionSementeImpiego,
    ) -> tuple[int | None, CommissionSementeImpiegoResult | None]:
        cursor.execute(
            """INSERT INTO tpo.semente_impiego_commissioning_requests
               (operation_scope,idempotency_key,canonical_payload_hash,
                semente_impiego_id,outcome,recorded_at,created_by)
               VALUES (%s,%s,%s,NULL,'RESERVED',CURRENT_TIMESTAMP,%s)
               ON CONFLICT (operation_scope,idempotency_key) DO NOTHING
               RETURNING id""",
            (SCOPE, command.authority.idempotency_key,
             command.canonical_payload_hash, command.authority.actor.value),
        )
        row = cursor.fetchone()
        if row is not None:
            return row[0], None
        return None, PostgreSQLSementeImpiegoCommissioningWriter._replay(cursor, command)

    @staticmethod
    def _replay(cursor: Any, command: CommissionSementeImpiego) -> CommissionSementeImpiegoResult:
        cursor.execute(
            """SELECT r.canonical_payload_hash,r.outcome,si.id,s.fornitore,
                      s.referenza_commerciale,v.public_id,c.denominazione,u.denominazione,
                      si.raccomandazione,si.rating,si.motivazione,si.ultima_revisione,
                      r.recorded_at
               FROM tpo.semente_impiego_commissioning_requests r
               JOIN tpo.semente_impieghi si ON si.id=r.semente_impiego_id
               JOIN tpo.sementi s ON s.id=si.semente_id
               JOIN tpo.cultivar_usi cu ON cu.id=si.cultivar_uso_id
               JOIN tpo.cultivar c ON c.id=cu.cultivar_id
               JOIN tpo.varieta v ON v.id=c.varieta_id
               JOIN tpo.usi_produttivi u ON u.id=cu.uso_produttivo_id
               WHERE r.operation_scope=%s AND r.idempotency_key=%s
               FOR UPDATE OF r""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if row is None:
            raise SementeImpiegoReconciliationRequiredError(
                "Reservation idempotency concorrente non leggibile."
            )
        if row[0] != command.canonical_payload_hash:
            raise SementeImpiegoIdempotencyConflictError(
                "Stessa idempotency key con payload differente."
            )
        if row[1] != "COMMITTED":
            raise SementeImpiegoReconciliationRequiredError(
                "Reservation idempotency priva di risultato committed."
            )
        return CommissionSementeImpiegoResult(
            row[2], "COMPATIBLE_REPLAY", row[3], row[4], row[5], row[6], row[7],
            SementeRaccomandazione(row[8]), row[9], row[10], row[11], row[12],
        )

    @staticmethod
    def _semente(cursor: Any, command: CommissionSementeImpiego) -> int:
        cursor.execute(
            """SELECT id,attiva FROM tpo.sementi
               WHERE lower(btrim(fornitore))=lower(btrim(%s))
                 AND lower(btrim(referenza_commerciale))=lower(btrim(%s))
               FOR SHARE""",
            (command.fornitore, command.referenza_commerciale),
        )
        rows = cursor.fetchall()
        if not rows:
            raise SementeAuthorityNotFoundError("SEMENTE autorevole inesistente.")
        if len(rows) != 1:
            raise SementeAuthorityAmbiguousError("SEMENTE autorevole ambigua.")
        if not rows[0][1]:
            raise SementeAuthorityInactiveError("SEMENTE autorevole inattiva.")
        return rows[0][0]

    @staticmethod
    def _context(cursor: Any, command: CommissionSementeImpiego, semente_id: int) -> tuple[Any, ...]:
        cursor.execute(
            """SELECT cu.id,v.public_id,c.denominazione,u.denominazione
               FROM tpo.protocollo_versioni pv
               JOIN tpo.protocolli p ON p.id=pv.protocollo_id
               JOIN tpo.cultivar_usi cu ON cu.id=p.cultivar_uso_id
               JOIN tpo.cultivar c ON c.id=cu.cultivar_id
               JOIN tpo.varieta v ON v.id=c.varieta_id
               JOIN tpo.usi_produttivi u ON u.id=cu.uso_produttivo_id
               WHERE pv.public_id=%s AND pv.stato_approvazione='APPROVATA'
                 AND pv.valida_dal<=CURRENT_DATE AND (pv.valida_al IS NULL OR pv.valida_al>CURRENT_DATE)
                 AND p.attivo AND cu.stato_validazione='APPROVATA'
                 AND c.stato='ATTIVA' AND v.stato='ATTIVA' AND u.attivo
               FOR SHARE OF pv,p,cu,c,v,u""",
            (command.protocol_version_public_id.value,),
        )
        rows = cursor.fetchall()
        if len(rows) != 1:
            raise ProtocolContextUnavailableError(
                "PV assente, non approvata o contesto CULTIVAR_USO non eleggibile."
            )
        return rows[0]

    @staticmethod
    def _assert_not_duplicate(cursor: Any, semente_id: int, cultivar_uso_id: int) -> None:
        cursor.execute(
            """SELECT id FROM tpo.semente_impieghi
               WHERE semente_id=%s AND cultivar_uso_id=%s FOR UPDATE""",
            (semente_id, cultivar_uso_id),
        )
        if cursor.fetchone() is not None:
            raise SementeImpiegoDuplicateError(
                "SEMENTE_IMPIEGO già commissionata con altra request authority."
            )

    @staticmethod
    def _audit(cursor: Any, impiego_pk: int, command: CommissionSementeImpiego,
               context: tuple[Any, ...], recorded_at: Any) -> None:
        after = {
            "internal_id": impiego_pk,
            "fornitore": command.fornitore,
            "referenza_commerciale": command.referenza_commerciale,
            "varieta_public_id": context[1], "cultivar": context[2], "uso_produttivo": context[3],
            "protocol_version_public_id": command.protocol_version_public_id.value,
            "raccomandazione": command.raccomandazione.value,
            "rating": str(command.rating) if command.rating is not None else None,
            "motivazione": command.motivazione,
            "idempotency_key": command.authority.idempotency_key,
            "canonical_payload_hash": command.canonical_payload_hash,
        }
        cursor.execute(
            """INSERT INTO tpo.audit_eventi
               (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                after_data,correlation_id,provenance)
               VALUES (%s,%s,'SEMENTE_IMPIEGO',NULL,'INSERT',%s,%s,%s,%s)""",
            (recorded_at, command.authority.actor.value,
             command.authority.reason, Jsonb(after), command.authority.correlation_id,
             json.dumps({"boundary": "semente-impiego-commissioning-v1"}, sort_keys=True)),
        )

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "")
        if name == "uq_semente_impiego_commissioning_request_key":
            return SementeImpiegoReconciliationRequiredError(
                "Collisione idempotency inattesa da riconciliare."
            )
        if name == "uq_semente_impieghi_semente_cultivar_uso":
            return SementeImpiegoDuplicateError("SEMENTE_IMPIEGO già commissionata.")
        return SementeImpiegoCommitRolledBackError("Vincolo SEMENTE_IMPIEGO non soddisfatto.")


def _result(impiego_pk: int, command: CommissionSementeImpiego, context: tuple[Any, ...],
            ultima_revisione: Any, recorded_at: Any, outcome: str) -> CommissionSementeImpiegoResult:
    return CommissionSementeImpiegoResult(
        impiego_pk, outcome, command.fornitore, command.referenza_commerciale,
        context[1], context[2], context[3], command.raccomandazione, command.rating,
        command.motivazione, ultima_revisione, recorded_at,
    )
