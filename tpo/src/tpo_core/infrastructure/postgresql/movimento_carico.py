"""Writer PostgreSQL atomico per Movimento Carico Raccolta Boundary V1.

Autorità: docs/architecture/MOVIMENTO_CARICO_AUTHORITY_FREEZE.md. Implementa
la riserva di RACCOLTA_AUTHORITY_FREEZE.md Sezione 11: pubblica un CARICO
originato da una RACCOLTA reale e incrementa lo STOCK della VARIETA
corrispondente (risolta da raccolta.semina_id -> semina.varieta_id, mai
input diretto del chiamante). La quantità in GRAM è dichiarata
dall'operatore (Owner Decision D11); raccolta_id sul MOVIMENTO è un
riferimento di tracciabilità, non un vincolo di quantità massima cumulabile
(Owner Decision D12: più CARICHI parziali per la stessa RACCOLTA sono
ammessi, nessuna colonna UNIQUE su raccolta_id).
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.movimento_carico.errors import (
    MovimentoCaricoCommitOutcomeUncertainError,
    MovimentoCaricoCommitRolledBackError,
    MovimentoCaricoConcurrencyError,
    MovimentoCaricoIdempotencyConflictError,
    MovimentoCaricoIdentityUnavailableError,
    MovimentoCaricoPersistenceInvariantError,
    MovimentoCaricoRaccoltaNotFoundError,
    MovimentoCaricoReconciliationRequiredError,
    MovimentoCaricoStockUnitMismatchError,
)
from ...application.movimento_carico.models import (
    RegistraCaricoMagazzino, RegistraCaricoMagazzinoResult,
)
from ...domain.identifiers import MovimentoId, RaccoltaId, VarietaId
from .connection import PostgreSQLConnectionFactory

SCOPE = "MOVIMENTO_CARICO_RACCOLTA_V1"


class PostgreSQLMovimentoCaricoWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def registra(self, command: RegistraCaricoMagazzino) -> RegistraCaricoMagazzinoResult:
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
                raise MovimentoCaricoReconciliationRequiredError(
                    "Reservation MOVIMENTO_CARICO non riconciliabile."
                )
            raccolta_pk, semina_pk = self._lock_raccolta(cursor, command)
            varieta_pk, varieta_public_id = self._resolve_varieta(cursor, semina_pk)
            self._lock_or_create_stock(cursor, varieta_pk)
            public_id, sequence = self._allocate(cursor)
            cursor.execute(
                """INSERT INTO tpo.movimenti_magazzino
                   (public_id,varieta_id,unita_misura,tipo,direzione,quantita,
                    data_movimento,motivo,origine_tipo,origine_riferimento,
                    raccolta_id,created_by)
                   VALUES (%s,%s,'GRAM','CARICO','POSITIVO',%s,%s,%s,'RACCOLTA',
                           %s,%s,%s) RETURNING id,created_at""",
                (public_id.value, varieta_pk, command.quantita_pesata,
                 command.effective_at, command.motivo, command.raccolta_id.value,
                 raccolta_pk, command.authority.actor.value),
            )
            movimento_pk, recorded_at = cursor.fetchone()
            cursor.execute(
                """UPDATE tpo.stock SET disponibile=disponibile+%s,
                          ultimo_movimento_id=%s,updated_at=%s,version=version+1
                   WHERE varieta_id=%s""",
                (command.quantita_pesata, movimento_pk, recorded_at, varieta_pk),
            )
            if cursor.rowcount != 1:
                raise MovimentoCaricoConcurrencyError("STOCK non aggiornabile.")
            cursor.execute(
                "SELECT disponibile FROM tpo.stock WHERE varieta_id=%s", (varieta_pk,),
            )
            stock_disponibile = Decimal(cursor.fetchone()[0])
            after = {
                "public_id": public_id.value,
                "raccolta_id": command.raccolta_id.value,
                "varieta_id": varieta_public_id,
                "quantita_pesata": str(command.quantita_pesata),
                "uom": "GRAM",
                "effective_at": command.effective_at.isoformat(),
                "recorded_at": recorded_at.isoformat(),
                "motivo": command.motivo,
                "stock_disponibile_dopo": str(stock_disponibile),
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'MOVIMENTO_MAGAZZINO',%s,'INSERT',%s,NULL,%s,%s,%s)""",
                (recorded_at, command.authority.actor.value, public_id.value,
                 command.authority.reason, Jsonb(after), command.authority.correlation_id,
                 json.dumps({"boundary": "movimento-carico-raccolta-v1",
                             "idempotency_key": command.authority.idempotency_key},
                            sort_keys=True)),
            )
            cursor.execute(
                """UPDATE tpo.movimento_carico_requests
                   SET movimento_id=%s,result_public_id=%s,outcome='COMMITTED'
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (movimento_pk, public_id.value, reservation, command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise MovimentoCaricoReconciliationRequiredError(
                    "Reservation MOVIMENTO_CARICO non aggiornabile."
                )
            cursor.execute(
                """UPDATE tpo.id_sequences SET next_value=%s,version=version+1,
                   updated_at=%s,updated_by=%s WHERE sequence_name=%s
                   AND identifier_type=%s AND prefix=%s AND next_value=%s AND version=%s""",
                (sequence[3] + 1, recorded_at, command.authority.actor.value,
                 MovimentoId.sequence_name, MovimentoId.__name__, MovimentoId.prefix,
                 sequence[3], sequence[4]),
            )
            if cursor.rowcount != 1:
                raise MovimentoCaricoIdentityUnavailableError("Conflitto contatore MOVIMENTO_ID.")
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = RegistraCaricoMagazzinoResult(
                public_id, command.raccolta_id, VarietaId(varieta_public_id),
                command.quantita_pesata, command.effective_at, recorded_at,
                stock_disponibile, "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise MovimentoCaricoCommitOutcomeUncertainError(
                    "Esito commit MOVIMENTO_CARICO da riconciliare tramite idempotency_key."
                ) from exc
            committed = True
            return result
        except (MovimentoCaricoRaccoltaNotFoundError, MovimentoCaricoStockUnitMismatchError,
                MovimentoCaricoIdempotencyConflictError, MovimentoCaricoReconciliationRequiredError,
                MovimentoCaricoConcurrencyError, MovimentoCaricoIdentityUnavailableError,
                MovimentoCaricoCommitOutcomeUncertainError, MovimentoCaricoPersistenceInvariantError):
            raise
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise MovimentoCaricoCommitRolledBackError(
                "MOVIMENTO_CARICO fallito con rollback certo."
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
    def _reserve_or_replay(
        cursor: Any, command: RegistraCaricoMagazzino,
    ) -> tuple[int | None, RegistraCaricoMagazzinoResult | None]:
        cursor.execute(
            """INSERT INTO tpo.movimento_carico_requests
               (operation_scope,idempotency_key,canonical_payload_hash,
                movimento_id,result_public_id,outcome,recorded_at,created_by)
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
            """SELECT q.canonical_payload_hash,q.outcome,m.public_id,m.raccolta_id,
                      v.public_id,m.quantita,m.data_movimento,q.recorded_at,s.disponibile
               FROM tpo.movimento_carico_requests q
               LEFT JOIN tpo.movimenti_magazzino m ON m.id=q.movimento_id
               LEFT JOIN tpo.varieta v ON v.id=m.varieta_id
               LEFT JOIN tpo.stock s ON s.varieta_id=m.varieta_id
               WHERE q.operation_scope=%s AND q.idempotency_key=%s FOR UPDATE OF q""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if row is None:
            raise MovimentoCaricoReconciliationRequiredError(
                "Reservation MOVIMENTO_CARICO concorrente non leggibile."
            )
        if row[0] != command.canonical_payload_hash:
            raise MovimentoCaricoIdempotencyConflictError(
                "Stessa idempotency key con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise MovimentoCaricoReconciliationRequiredError(
                "Reservation MOVIMENTO_CARICO priva di risultato committed."
            )
        cursor.execute(
            "SELECT public_id FROM tpo.raccolte WHERE id=%s", (row[3],),
        )
        raccolta_row = cursor.fetchone()
        if raccolta_row is None:
            raise MovimentoCaricoPersistenceInvariantError(
                "Risultato MOVIMENTO_CARICO persistito invalido."
            )
        return None, RegistraCaricoMagazzinoResult(
            MovimentoId(row[2]), RaccoltaId(raccolta_row[0]), VarietaId(row[4]),
            Decimal(row[5]), row[6], row[7], Decimal(row[8]), "COMPATIBLE_REPLAY",
        )

    @staticmethod
    def _lock_raccolta(cursor: Any, command: RegistraCaricoMagazzino) -> tuple[int, int]:
        cursor.execute(
            "SELECT id,semina_id FROM tpo.raccolte WHERE public_id=%s FOR SHARE",
            (command.raccolta_id.value,),
        )
        row = cursor.fetchone()
        if row is None:
            raise MovimentoCaricoRaccoltaNotFoundError("RACCOLTA inesistente.")
        return row[0], row[1]

    @staticmethod
    def _resolve_varieta(cursor: Any, semina_pk: int) -> tuple[int, str]:
        cursor.execute(
            """SELECT v.id,v.public_id FROM tpo.semine s
               JOIN tpo.varieta v ON v.id=s.varieta_id WHERE s.id=%s""",
            (semina_pk,),
        )
        row = cursor.fetchone()
        if row is None:
            raise MovimentoCaricoPersistenceInvariantError(
                "SEMINA della RACCOLTA priva di VARIETA risolvibile."
            )
        return row[0], row[1]

    @staticmethod
    def _lock_or_create_stock(cursor: Any, varieta_pk: int) -> None:
        cursor.execute(
            """INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at,version)
               VALUES (%s,0,'GRAM',CURRENT_TIMESTAMP,0)
               ON CONFLICT (varieta_id) DO NOTHING""",
            (varieta_pk,),
        )
        cursor.execute(
            "SELECT unita_misura FROM tpo.stock WHERE varieta_id=%s FOR UPDATE",
            (varieta_pk,),
        )
        row = cursor.fetchone()
        if row is None or row[0] != "GRAM":
            raise MovimentoCaricoStockUnitMismatchError(
                "STOCK esistente per questa VARIETA non è in GRAM."
            )

    @staticmethod
    def _allocate(cursor: Any) -> tuple[MovimentoId, tuple[Any, ...]]:
        cursor.execute(
            """SELECT sequence_name,identifier_type,prefix,next_value,version
               FROM tpo.id_sequences WHERE sequence_name=%s FOR UPDATE""",
            (MovimentoId.sequence_name,),
        )
        row = cursor.fetchone()
        if not row or row[1] != MovimentoId.__name__ or row[2] != MovimentoId.prefix:
            raise MovimentoCaricoIdentityUnavailableError("MOVIMENTO_ID assente o incompatibile.")
        try:
            return MovimentoId(f"{row[2]}-{row[3]:06d}"), row
        except Exception as exc:
            raise MovimentoCaricoIdentityUnavailableError("MOVIMENTO_ID malformata.") from exc

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if name == "uq_movimento_carico_request_key":
            return MovimentoCaricoReconciliationRequiredError(
                "Collisione idempotency inattesa da riconciliare."
            )
        if name in {"movimenti_magazzino_public_id_key", "ck_movimenti_magazzino_public_id_format"}:
            return MovimentoCaricoIdentityUnavailableError("Collisione MOV identity.")
        if name.startswith("ck_movimenti_magazzino_") or name == "ck_stock_disponibile_nonnegative":
            return MovimentoCaricoPersistenceInvariantError("Vincolo MOVIMENTO_CARICO non soddisfatto.")
        return MovimentoCaricoCommitRolledBackError("Vincolo MOVIMENTO_CARICO non soddisfatto.")
