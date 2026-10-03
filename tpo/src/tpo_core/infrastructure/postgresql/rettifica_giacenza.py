"""Writer PostgreSQL atomico del boundary RETTIFICA_GIACENZA V1.

Riduce lo STOCK di una VARIETA/unita' quando la merce che il sistema crede
presente non esiste piu' fisicamente (es. venduta senza registrazione). Non
modifica nessun fatto gia' committato: scrive un nuovo MOVIMENTO SCARICO
(origine_tipo 'RETTIFICA_GIACENZA'), spiega i lotti di provenienza con
CONSUMO_LOTTO (tipo 'RETTIFICA_GIACENZA') e un audit event, tutto nello stesso
commit. Idempotenza: tpo.movimento_carico_requests con scope
MOVIMENTO_RETTIFICA_GIACENZA_V1 (migrazione 20261003_0037).
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.rettifica_giacenza.errors import (
    RettificaGiacenzaCommitOutcomeUncertainError,
    RettificaGiacenzaCommitRolledBackError,
    RettificaGiacenzaConcurrencyError,
    RettificaGiacenzaError,
    RettificaGiacenzaIdempotencyConflictError,
    RettificaGiacenzaIdentityUnavailableError,
    RettificaGiacenzaOrigineError,
    RettificaGiacenzaPersistenceInvariantError,
    RettificaGiacenzaReconciliationRequiredError,
    RettificaGiacenzaStockError,
    RettificaGiacenzaVarietaNotFoundError,
)
from ...application.rettifica_giacenza.models import RettificaGiacenza, RettificaGiacenzaResult
from ...domain.identifiers import MovimentoId, VarietaId
from ...domain.quantities import UnitOfMeasure
from .connection import PostgreSQLConnectionFactory
from .consumo_lotto import consume_lots

SCOPE = "MOVIMENTO_RETTIFICA_GIACENZA_V1"
ORIGINE_TIPO = "RETTIFICA_GIACENZA"


class PostgreSQLRettificaGiacenzaWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def registra(self, command: RettificaGiacenza) -> RettificaGiacenzaResult:
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
                raise RettificaGiacenzaReconciliationRequiredError(
                    "Reservation RETTIFICA_GIACENZA non riconciliabile."
                )
            cursor.execute(
                "SELECT id FROM tpo.varieta WHERE public_id=%s FOR SHARE",
                (command.varieta_id.value,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RettificaGiacenzaVarietaNotFoundError("VARIETA inesistente.")
            varieta_pk = row[0]
            unit = command.unita_misura.value
            cursor.execute(
                """SELECT disponibile FROM tpo.stock
                   WHERE varieta_id=%s AND unita_misura=%s FOR UPDATE""",
                (varieta_pk, unit),
            )
            stock_row = cursor.fetchone()
            if stock_row is None or Decimal(stock_row[0]) < command.quantita:
                disponibile = Decimal(0) if stock_row is None else Decimal(stock_row[0])
                raise RettificaGiacenzaStockError(
                    f"STOCK insufficiente: disponibile {disponibile} {unit}, "
                    f"rettifica richiesta {command.quantita} {unit}."
                )
            public_id, sequence = self._allocate(cursor)
            cursor.execute(
                """INSERT INTO tpo.movimenti_magazzino
                   (public_id,varieta_id,unita_misura,tipo,direzione,quantita,
                    data_movimento,motivo,origine_tipo,created_by)
                   VALUES (%s,%s,%s,'SCARICO','NEGATIVO',%s,%s,%s,%s,%s)
                   RETURNING id,created_at""",
                (public_id.value, varieta_pk, unit, command.quantita,
                 command.effective_at, command.motivo, ORIGINE_TIPO,
                 command.authority.actor.value),
            )
            movimento_pk, recorded_at = cursor.fetchone()
            cursor.execute(
                """UPDATE tpo.stock SET disponibile=disponibile-%s,
                          ultimo_movimento_id=%s,updated_at=%s,version=version+1
                   WHERE varieta_id=%s AND unita_misura=%s AND disponibile>=%s""",
                (command.quantita, movimento_pk, recorded_at, varieta_pk, unit,
                 command.quantita),
            )
            if cursor.rowcount != 1:
                raise RettificaGiacenzaConcurrencyError("STOCK non aggiornabile.")
            # La giacenza e' gia' stata decrementata: consume_lots ricava la
            # parte senza origine (D5) con la stessa formula usata per le consegne.
            consume_lots(
                cursor, varieta_pk=varieta_pk, unit=unit,
                movimento_scarico_id=movimento_pk, quantity_needed=command.quantita,
                persistence_at=recorded_at, actor=command.authority.actor.value,
                tipo_consumo=ORIGINE_TIPO,
                origin_semina=(
                    None if command.origin_semina is None else command.origin_semina.value
                ),
                fail=RettificaGiacenzaOrigineError,
            )
            cursor.execute(
                "SELECT disponibile FROM tpo.stock WHERE varieta_id=%s AND unita_misura=%s",
                (varieta_pk, unit),
            )
            stock_disponibile = Decimal(cursor.fetchone()[0])
            after = {
                "public_id": public_id.value,
                "varieta_id": command.varieta_id.value,
                "quantita": str(command.quantita),
                "uom": unit,
                "effective_at": command.effective_at.isoformat(),
                "recorded_at": recorded_at.isoformat(),
                "motivo": command.motivo,
                "origine_tipo": ORIGINE_TIPO,
                "origin_semina": (
                    None if command.origin_semina is None else command.origin_semina.value
                ),
                "stock_disponibile_dopo": str(stock_disponibile),
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'MOVIMENTO_MAGAZZINO',%s,'INSERT',%s,NULL,%s,%s,%s)""",
                (recorded_at, command.authority.actor.value, public_id.value,
                 command.authority.reason, Jsonb(after), command.authority.correlation_id,
                 json.dumps({"boundary": "rettifica-giacenza-v1",
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
                raise RettificaGiacenzaReconciliationRequiredError(
                    "Reservation RETTIFICA_GIACENZA non aggiornabile."
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
                raise RettificaGiacenzaIdentityUnavailableError(
                    "Conflitto contatore MOVIMENTO_ID."
                )
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = RettificaGiacenzaResult(
                public_id, command.varieta_id, command.unita_misura, command.quantita,
                command.effective_at, recorded_at, stock_disponibile, "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise RettificaGiacenzaCommitOutcomeUncertainError(
                    "Esito commit RETTIFICA_GIACENZA da riconciliare tramite idempotency_key."
                ) from exc
            committed = True
            return result
        except RettificaGiacenzaError:
            raise
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise RettificaGiacenzaCommitRolledBackError(
                "RETTIFICA_GIACENZA fallita con rollback certo."
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
        cursor: Any, command: RettificaGiacenza,
    ) -> tuple[int | None, RettificaGiacenzaResult | None]:
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
            """SELECT q.canonical_payload_hash,q.outcome,m.public_id,v.public_id,
                      m.quantita,m.unita_misura,m.data_movimento,q.recorded_at,s.disponibile
               FROM tpo.movimento_carico_requests q
               LEFT JOIN tpo.movimenti_magazzino m ON m.id=q.movimento_id
               LEFT JOIN tpo.varieta v ON v.id=m.varieta_id
               LEFT JOIN tpo.stock s ON s.varieta_id=m.varieta_id AND s.unita_misura=m.unita_misura
               WHERE q.operation_scope=%s AND q.idempotency_key=%s FOR UPDATE OF q""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if row is None:
            raise RettificaGiacenzaReconciliationRequiredError(
                "Reservation RETTIFICA_GIACENZA concorrente non leggibile."
            )
        if row[0] != command.canonical_payload_hash:
            raise RettificaGiacenzaIdempotencyConflictError(
                "Stessa idempotency key con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise RettificaGiacenzaReconciliationRequiredError(
                "Reservation RETTIFICA_GIACENZA priva di risultato committed."
            )
        return None, RettificaGiacenzaResult(
            MovimentoId(row[2]), VarietaId(row[3]), UnitOfMeasure(row[5]),
            Decimal(row[4]), row[6], row[7], Decimal(row[8]), "COMPATIBLE_REPLAY",
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
            raise RettificaGiacenzaIdentityUnavailableError("MOVIMENTO_ID assente o incompatibile.")
        try:
            return MovimentoId(f"{row[2]}-{row[3]:06d}"), row
        except Exception as exc:
            raise RettificaGiacenzaIdentityUnavailableError("MOVIMENTO_ID malformata.") from exc

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if name == "uq_movimento_carico_request_key":
            return RettificaGiacenzaReconciliationRequiredError(
                "Collisione idempotency inattesa da riconciliare."
            )
        if name in {"movimenti_magazzino_public_id_key", "ck_movimenti_magazzino_public_id_format"}:
            return RettificaGiacenzaIdentityUnavailableError("Collisione MOV identity.")
        if name.startswith("ck_movimenti_magazzino_") or name == "ck_stock_disponibile_nonnegative":
            return RettificaGiacenzaPersistenceInvariantError(
                "Vincolo RETTIFICA_GIACENZA non soddisfatto."
            )
        return RettificaGiacenzaCommitRolledBackError("Vincolo RETTIFICA_GIACENZA non soddisfatto.")
