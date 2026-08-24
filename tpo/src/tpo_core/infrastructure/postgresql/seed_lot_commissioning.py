"""Atomic PostgreSQL writer for Seed Lot Commissioning V1."""

from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.seed_lot_commissioning.errors import (
    SeedAuthorityAmbiguousError, SeedAuthorityInactiveError,
    SeedAuthorityNotFoundError, SeedLotCommitRolledBackError,
    SeedLotConcurrencyConflictError, SeedLotDuplicateError,
    SeedLotIdempotencyConflictError, SeedLotIdentityUnavailableError,
    SeedLotReconciliationRequiredError,
)
from ...application.seed_lot_commissioning.models import (
    CommissionSeedLot, CommissionSeedLotResult,
)
from ...domain.identifiers import LottoSemeId
from ...domain.quantities import Quantity, UnitOfMeasure
from .connection import PostgreSQLConnectionFactory

SCOPE = "SEED_LOT_COMMISSIONING_V1"


class PostgreSQLSeedLotCommissioningWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def commission(self, command: CommissionSeedLot) -> CommissionSeedLotResult:
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
                raise SeedLotReconciliationRequiredError(
                    "Reservation idempotency non riconciliabile."
                )
            seed_id = self._seed(cursor, command)
            self._assert_not_duplicate(cursor, seed_id, command.manufacturer_lot_number)
            public_id, sequence = self._allocate(cursor)
            cursor.execute(
                """INSERT INTO tpo.lotti_seme
                   (public_id,semente_id,numero_lotto_produttore,data_ricezione,
                    data_scadenza,quantita_iniziale,quantita_residua,unita_misura,
                    anomalia,created_by,updated_at,updated_by,version)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'GRAM',%s,%s,CURRENT_TIMESTAMP,%s,0)
                   RETURNING id,created_at""",
                (public_id.value, seed_id, command.manufacturer_lot_number,
                 command.received_date, command.expiry_date,
                 command.initial_quantity.value, command.initial_quantity.value,
                 command.anomaly, command.authority.actor.value,
                 command.authority.actor.value),
            )
            lot_pk, recorded_at = cursor.fetchone()
            cursor.execute(
                """UPDATE tpo.seed_lot_commissioning_requests
                   SET seed_lot_id=%s,result_public_id=%s,outcome='COMMITTED',recorded_at=%s
                   WHERE id=%s AND operation_scope=%s
                     AND canonical_payload_hash=%s AND outcome='RESERVED'
                     AND seed_lot_id IS NULL AND result_public_id IS NULL""",
                (lot_pk, public_id.value, recorded_at, reservation_id, SCOPE,
                 command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise SeedLotConcurrencyConflictError(
                    "Reservation idempotency non aggiornabile."
                )
            self._audit(cursor, lot_pk, public_id, command, recorded_at)
            cursor.execute(
                """UPDATE tpo.id_sequences
                   SET next_value=%s,version=version+1,updated_at=CURRENT_TIMESTAMP,updated_by=%s
                   WHERE sequence_name=%s AND identifier_type=%s AND prefix=%s
                     AND next_value=%s AND version=%s""",
                (sequence[3] + 1, command.authority.actor.value,
                 LottoSemeId.sequence_name, LottoSemeId.__name__, LottoSemeId.prefix,
                 sequence[3], sequence[4]),
            )
            if cursor.rowcount != 1:
                raise SeedLotConcurrencyConflictError("Identity allocation conflict.")
            result = _result(public_id, command, recorded_at, "INSERTED")
            try:
                connection.commit()
            except Exception as exc:
                raise SeedLotReconciliationRequiredError(
                    "Esito commit LOTTO_SEME da riconciliare."
                ) from exc
            committed = True
            return result
        except (SeedAuthorityNotFoundError, SeedAuthorityInactiveError,
                SeedAuthorityAmbiguousError, SeedLotDuplicateError,
                SeedLotIdempotencyConflictError, SeedLotIdentityUnavailableError,
                SeedLotConcurrencyConflictError, SeedLotReconciliationRequiredError):
            raise
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise SeedLotCommitRolledBackError(
                "Commissioning LOTTO_SEME fallito con rollback certo."
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
        cursor: Any, command: CommissionSeedLot,
    ) -> tuple[int | None, CommissionSeedLotResult | None]:
        cursor.execute(
            """INSERT INTO tpo.seed_lot_commissioning_requests
               (operation_scope,idempotency_key,canonical_payload_hash,
                seed_lot_id,result_public_id,outcome,recorded_at,created_by)
               VALUES (%s,%s,%s,NULL,NULL,'RESERVED',CURRENT_TIMESTAMP,%s)
               ON CONFLICT (operation_scope,idempotency_key) DO NOTHING
               RETURNING id""",
            (SCOPE, command.authority.idempotency_key,
             command.canonical_payload_hash, command.authority.actor.value),
        )
        row = cursor.fetchone()
        if row is not None:
            return row[0], None
        return None, PostgreSQLSeedLotCommissioningWriter._replay(cursor, command)

    @staticmethod
    def _replay(cursor: Any, command: CommissionSeedLot) -> CommissionSeedLotResult:
        cursor.execute(
            """SELECT r.canonical_payload_hash,r.outcome,l.public_id,s.fornitore,
                      s.referenza_commerciale,l.numero_lotto_produttore,
                      l.quantita_iniziale,l.quantita_residua,l.data_ricezione,
                      l.data_scadenza,r.recorded_at
               FROM tpo.seed_lot_commissioning_requests r
               JOIN tpo.lotti_seme l ON l.id=r.seed_lot_id
               JOIN tpo.sementi s ON s.id=l.semente_id
               WHERE r.operation_scope=%s AND r.idempotency_key=%s
               FOR UPDATE OF r""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if row is None:
            raise SeedLotReconciliationRequiredError(
                "Reservation idempotency concorrente non leggibile."
            )
        if row[0] != command.canonical_payload_hash:
            raise SeedLotIdempotencyConflictError("Stessa idempotency key con payload differente.")
        if row[1] != "COMMITTED":
            raise SeedLotReconciliationRequiredError(
                "Reservation idempotency priva di risultato committed."
            )
        return CommissionSeedLotResult(
            LottoSemeId(row[2]), "COMPATIBLE_REPLAY", row[3], row[4], row[5],
            Quantity(row[6], UnitOfMeasure.GRAM), Quantity(row[7], UnitOfMeasure.GRAM),
            row[8], row[9], row[10],
        )

    @staticmethod
    def _seed(cursor: Any, command: CommissionSeedLot) -> int:
        cursor.execute(
            """SELECT id,attiva FROM tpo.sementi
               WHERE lower(btrim(fornitore))=lower(btrim(%s))
                 AND lower(btrim(referenza_commerciale))=lower(btrim(%s))
               FOR SHARE""",
            (command.seed_supplier, command.seed_commercial_reference),
        )
        rows = cursor.fetchall()
        if not rows:
            raise SeedAuthorityNotFoundError("SEMENTE autorevole inesistente.")
        if len(rows) != 1:
            raise SeedAuthorityAmbiguousError("SEMENTE autorevole ambigua.")
        if not rows[0][1]:
            raise SeedAuthorityInactiveError("SEMENTE autorevole inattiva.")
        return rows[0][0]

    @staticmethod
    def _assert_not_duplicate(cursor: Any, seed_id: int, lot: str) -> None:
        cursor.execute(
            """SELECT public_id FROM tpo.lotti_seme
               WHERE semente_id=%s AND numero_lotto_produttore=%s FOR UPDATE""",
            (seed_id, lot),
        )
        if cursor.fetchone() is not None:
            raise SeedLotDuplicateError("Lotto fisico già commissionato con altra request authority.")

    @staticmethod
    def _allocate(cursor: Any) -> tuple[LottoSemeId, tuple[Any, ...]]:
        cursor.execute(
            """SELECT sequence_name,identifier_type,prefix,next_value,version
               FROM tpo.id_sequences WHERE sequence_name=%s FOR UPDATE""",
            (LottoSemeId.sequence_name,),
        )
        row = cursor.fetchone()
        if row is None or row[1] != LottoSemeId.__name__ or row[2] != LottoSemeId.prefix:
            raise SeedLotIdentityUnavailableError("LOTTO_SEME_ID assente o incompatibile.")
        return LottoSemeId(f"{row[2]}-{row[3]:06d}"), row

    @staticmethod
    def _audit(cursor: Any, lot_pk: int, public_id: LottoSemeId,
               command: CommissionSeedLot, recorded_at: Any) -> None:
        after = {
            "public_id": public_id.value,
            "seed_supplier": command.seed_supplier,
            "seed_commercial_reference": command.seed_commercial_reference,
            "manufacturer_lot_number": command.manufacturer_lot_number,
            "received_date": command.received_date.isoformat(),
            "expiry_date": command.expiry_date.isoformat() if command.expiry_date else None,
            "initial_quantity": str(command.initial_quantity.value),
            "remaining_quantity": str(command.initial_quantity.value),
            "unit": "GRAM", "anomaly": command.anomaly,
            "idempotency_key": command.authority.idempotency_key,
            "canonical_payload_hash": command.canonical_payload_hash,
            "provenance": {field: source.value for field, source in command.provenance},
        }
        cursor.execute(
            """INSERT INTO tpo.audit_eventi
               (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                after_data,correlation_id,provenance)
               VALUES (%s,%s,'LOTTO_SEME',%s,'INSERT',%s,%s,%s,%s)""",
            (recorded_at, command.authority.actor.value, public_id.value,
             command.authority.reason, Jsonb(after), command.authority.correlation_id,
             json.dumps({"boundary": "seed-lot-commissioning-v1",
                         "facts": after["provenance"]}, sort_keys=True)),
        )

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "")
        if name == "uq_seed_lot_commissioning_request_key":
            return SeedLotReconciliationRequiredError(
                "Collisione idempotency inattesa da riconciliare."
            )
        if name == "uq_lotti_seme_semente_numero_lotto":
            return SeedLotDuplicateError("Lotto fisico già commissionato.")
        if name in {"uq_lotti_seme_public_id", "ck_lotti_seme_public_id"}:
            return SeedLotConcurrencyConflictError("Collisione LOTTO_SEME identity.")
        return SeedLotCommitRolledBackError("Vincolo LOTTO_SEME non soddisfatto.")


def _result(public_id: LottoSemeId, command: CommissionSeedLot,
            recorded_at: Any, outcome: str) -> CommissionSeedLotResult:
    return CommissionSeedLotResult(
        public_id, outcome, command.seed_supplier, command.seed_commercial_reference,
        command.manufacturer_lot_number, command.initial_quantity,
        command.initial_quantity, command.received_date, command.expiry_date, recorded_at,
    )
