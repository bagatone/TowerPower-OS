"""Writer PostgreSQL atomico per Movimento Articolo Boundary V1.

Autorità: docs/architecture/ARTICOLO_AUTHORITY_FREEZE.md. Pubblica un
MOVIMENTO_MAGAZZINO su un ARTICOLO, incrementando/decrementando lo
STOCK_ARTICOLI corrispondente (tabella parallela a tpo.stock, stessa forma).
Nessuna origine RACCOLTA/CONSEGNA (fisicamente non applicabile per ARTICOLO):
origine_tipo='ARTICOLO_MOVIMENTO', raccolta_id/consegna_id sempre NULL.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.movimento_articolo.errors import (
    MovimentoArticoloArticoloNotFoundError,
    MovimentoArticoloCommitOutcomeUncertainError,
    MovimentoArticoloCommitRolledBackError,
    MovimentoArticoloConcurrencyError,
    MovimentoArticoloIdempotencyConflictError,
    MovimentoArticoloIdentityUnavailableError,
    MovimentoArticoloInsufficientStockError,
    MovimentoArticoloPersistenceInvariantError,
    MovimentoArticoloReconciliationRequiredError,
    MovimentoArticoloStockUnitMismatchError,
)
from ...application.movimento_articolo.models import (
    RegistraMovimentoArticolo, RegistraMovimentoArticoloResult,
)
from ...domain.identifiers import ArticoloId, MovimentoId
from ...domain.states import MovimentoDirection
from .connection import PostgreSQLConnectionFactory

SCOPE = "MOVIMENTO_ARTICOLO_V1"
ORIGINE_TIPO = "ARTICOLO_MOVIMENTO"


class PostgreSQLMovimentoArticoloWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def registra(
        self, command: RegistraMovimentoArticolo
    ) -> RegistraMovimentoArticoloResult:
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
                raise MovimentoArticoloReconciliationRequiredError(
                    "Reservation MOVIMENTO_ARTICOLO non riconciliabile."
                )
            articolo_pk, articolo_public_id = self._lock_articolo(cursor, command)
            self._lock_or_create_stock_articoli(cursor, articolo_pk, command)
            delta = (command.quantita if command.direzione == MovimentoDirection.POSITIVO
                     else -command.quantita)
            public_id, sequence = self._allocate(cursor)
            cursor.execute(
                """INSERT INTO tpo.movimenti_magazzino
                   (public_id,articolo_id,unita_misura,tipo,direzione,quantita,
                    data_movimento,motivo,origine_tipo,origine_riferimento,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s) RETURNING id,created_at""",
                (public_id.value, articolo_pk, command.unita_misura, command.tipo.value,
                 command.direzione.value, command.quantita, command.effective_at,
                 command.motivo, ORIGINE_TIPO, command.authority.actor.value),
            )
            movimento_pk, recorded_at = cursor.fetchone()
            cursor.execute(
                """UPDATE tpo.stock_articoli SET disponibile=disponibile+%s,
                          ultimo_movimento_id=%s,updated_at=%s,version=version+1
                   WHERE articolo_id=%s""",
                (delta, movimento_pk, recorded_at, articolo_pk),
            )
            if cursor.rowcount != 1:
                raise MovimentoArticoloConcurrencyError("STOCK_ARTICOLI non aggiornabile.")
            cursor.execute(
                "SELECT disponibile FROM tpo.stock_articoli WHERE articolo_id=%s",
                (articolo_pk,),
            )
            stock_disponibile = Decimal(cursor.fetchone()[0])
            after = {
                "public_id": public_id.value,
                "articolo_id": articolo_public_id,
                "tipo": command.tipo.value,
                "direzione": command.direzione.value,
                "quantita": str(command.quantita),
                "uom": command.unita_misura,
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
                 json.dumps({"boundary": "movimento-articolo-v1",
                             "idempotency_key": command.authority.idempotency_key},
                            sort_keys=True)),
            )
            cursor.execute(
                """UPDATE tpo.movimento_articolo_requests
                   SET movimento_id=%s,result_public_id=%s,outcome='COMMITTED'
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (movimento_pk, public_id.value, reservation, command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise MovimentoArticoloReconciliationRequiredError(
                    "Reservation MOVIMENTO_ARTICOLO non aggiornabile."
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
                raise MovimentoArticoloIdentityUnavailableError(
                    "Conflitto contatore MOVIMENTO_ID."
                )
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = RegistraMovimentoArticoloResult(
                public_id, ArticoloId(articolo_public_id), command.quantita,
                command.unita_misura, command.effective_at, recorded_at,
                stock_disponibile, "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise MovimentoArticoloCommitOutcomeUncertainError(
                    "Esito commit MOVIMENTO_ARTICOLO da riconciliare tramite idempotency_key."
                ) from exc
            committed = True
            return result
        except (MovimentoArticoloArticoloNotFoundError, MovimentoArticoloStockUnitMismatchError,
                MovimentoArticoloIdempotencyConflictError, MovimentoArticoloReconciliationRequiredError,
                MovimentoArticoloConcurrencyError, MovimentoArticoloIdentityUnavailableError,
                MovimentoArticoloCommitOutcomeUncertainError, MovimentoArticoloPersistenceInvariantError,
                MovimentoArticoloInsufficientStockError):
            raise
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise MovimentoArticoloCommitRolledBackError(
                "MOVIMENTO_ARTICOLO fallito con rollback certo."
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
    def _reserve_or_replay(cursor: Any, command: RegistraMovimentoArticolo):
        cursor.execute(
            """INSERT INTO tpo.movimento_articolo_requests
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
            """SELECT q.canonical_payload_hash,q.outcome,m.public_id,a.public_id,
                      m.quantita,m.unita_misura,m.data_movimento,q.recorded_at,s.disponibile
               FROM tpo.movimento_articolo_requests q
               LEFT JOIN tpo.movimenti_magazzino m ON m.id=q.movimento_id
               LEFT JOIN tpo.articoli a ON a.id=m.articolo_id
               LEFT JOIN tpo.stock_articoli s ON s.articolo_id=m.articolo_id
               WHERE q.operation_scope=%s AND q.idempotency_key=%s FOR UPDATE OF q""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if row is None:
            raise MovimentoArticoloReconciliationRequiredError(
                "Reservation MOVIMENTO_ARTICOLO concorrente non leggibile."
            )
        if row[0] != command.canonical_payload_hash:
            raise MovimentoArticoloIdempotencyConflictError(
                "Stessa idempotency key con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise MovimentoArticoloReconciliationRequiredError(
                "Reservation MOVIMENTO_ARTICOLO priva di risultato committed."
            )
        return None, RegistraMovimentoArticoloResult(
            MovimentoId(row[2]), ArticoloId(row[3]), Decimal(row[4]), row[5],
            row[6], row[7], Decimal(row[8]), "COMPATIBLE_REPLAY",
        )

    @staticmethod
    def _lock_articolo(cursor: Any, command: RegistraMovimentoArticolo) -> tuple[int, str]:
        cursor.execute(
            "SELECT id,public_id FROM tpo.articoli WHERE public_id=%s FOR SHARE",
            (command.articolo_id.value,),
        )
        row = cursor.fetchone()
        if row is None:
            raise MovimentoArticoloArticoloNotFoundError("ARTICOLO inesistente.")
        return row[0], row[1]

    @staticmethod
    def _lock_or_create_stock_articoli(
        cursor: Any, articolo_pk: int, command: RegistraMovimentoArticolo,
    ) -> None:
        cursor.execute(
            """INSERT INTO tpo.stock_articoli(articolo_id,disponibile,unita_misura,
                                               updated_at,version)
               VALUES (%s,0,%s,CURRENT_TIMESTAMP,0)
               ON CONFLICT (articolo_id) DO NOTHING""",
            (articolo_pk, command.unita_misura),
        )
        cursor.execute(
            "SELECT disponibile,unita_misura FROM tpo.stock_articoli "
            "WHERE articolo_id=%s FOR UPDATE",
            (articolo_pk,),
        )
        row = cursor.fetchone()
        if row is None or row[1] != command.unita_misura:
            raise MovimentoArticoloStockUnitMismatchError(
                "STOCK_ARTICOLI esistente per questo ARTICOLO non è nell'unità dichiarata."
            )
        if (command.direzione == MovimentoDirection.NEGATIVO
                and Decimal(row[0]) < command.quantita):
            raise MovimentoArticoloInsufficientStockError(
                "STOCK_ARTICOLI disponibile insufficiente per questa variazione negativa."
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
            raise MovimentoArticoloIdentityUnavailableError(
                "MOVIMENTO_ID assente o incompatibile."
            )
        try:
            return MovimentoId(f"{row[2]}-{row[3]:06d}"), row
        except Exception as exc:
            raise MovimentoArticoloIdentityUnavailableError("MOVIMENTO_ID malformata.") from exc

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if name == "uq_movimento_articolo_request_key":
            return MovimentoArticoloReconciliationRequiredError(
                "Collisione idempotency inattesa da riconciliare."
            )
        if name in {"movimenti_magazzino_public_id_key", "ck_movimenti_magazzino_public_id_format"}:
            return MovimentoArticoloIdentityUnavailableError("Collisione MOV identity.")
        if (name.startswith("ck_movimenti_magazzino_")
                or name in {"ck_stock_articoli_disponibile_nonnegative",
                             "ck_movimenti_magazzino_risorsa_xor"}):
            return MovimentoArticoloPersistenceInvariantError(
                "Vincolo MOVIMENTO_ARTICOLO non soddisfatto."
            )
        return MovimentoArticoloCommitRolledBackError(
            "Vincolo MOVIMENTO_ARTICOLO non soddisfatto."
        )
