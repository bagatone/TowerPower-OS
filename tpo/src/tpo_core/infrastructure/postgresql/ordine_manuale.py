"""Writer PostgreSQL atomico del boundary ORDINE_MANUALE V1.

Pubblica un ORDINE ``MANUALE`` (vedi application/ordine_manuale/models.py) con
identita' ORD-/RO- allocate da tpo.id_sequences, righe, audit e idempotenza
(tpo.ordine_manuale_requests, migrazione 20261003_0037) nello stesso commit.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.ordine_manuale.errors import (
    OrdineManualeClienteNotFoundError,
    OrdineManualeCommitOutcomeUncertainError,
    OrdineManualeCommitRolledBackError,
    OrdineManualeError,
    OrdineManualeIdempotencyConflictError,
    OrdineManualeIdentityUnavailableError,
    OrdineManualePersistenceInvariantError,
    OrdineManualeReconciliationRequiredError,
    OrdineManualeVarietaError,
)
from ...application.ordine_manuale.models import (
    RegistraOrdineManuale, RegistraOrdineManualeResult, RigaOrdineRegistrata,
)
from ...domain.identifiers import ClienteId, OrdineId, RigaOrdineId, VarietaId
from ...domain.quantities import UnitOfMeasure
from .connection import PostgreSQLConnectionFactory

ORDINE_SEQUENCE = ("ORDINE_ID", "OrdineId", "ORD")
RIGA_SEQUENCE = (RigaOrdineId.sequence_name, RigaOrdineId.__name__, RigaOrdineId.prefix)


class PostgreSQLOrdineManualeWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def registra(self, command: RegistraOrdineManuale) -> RegistraOrdineManualeResult:
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
                raise OrdineManualeReconciliationRequiredError(
                    "Reservation ORDINE_MANUALE non riconciliabile."
                )
            actor = command.authority.actor.value
            cursor.execute(
                "SELECT id FROM tpo.clienti WHERE public_id=%s FOR SHARE",
                (command.client_id.value,),
            )
            client = cursor.fetchone()
            if client is None:
                raise OrdineManualeClienteNotFoundError("CLIENTE inesistente.")
            variety_pks: dict[str, int] = {}
            for riga in command.righe:
                cursor.execute(
                    "SELECT id,stato::text FROM tpo.varieta WHERE public_id=%s FOR SHARE",
                    (riga.varieta_id.value,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise OrdineManualeVarietaError(f"VARIETA {riga.varieta_id.value} inesistente.")
                if row[1] != "ATTIVA":
                    raise OrdineManualeVarietaError(
                        f"VARIETA {riga.varieta_id.value} non ATTIVA ({row[1]})."
                    )
                variety_pks[riga.varieta_id.value] = row[0]

            ordine_numero, ordine_sequence = self._allocate(cursor, ORDINE_SEQUENCE, 1)
            riga_numero, riga_sequence = self._allocate(cursor, RIGA_SEQUENCE, len(command.righe))
            ordine_id = OrdineId(f"ORD-{ordine_numero:06d}")
            cursor.execute(
                "SELECT 1 FROM tpo.ordini WHERE public_id=%s", (ordine_id.value,),
            )
            if cursor.fetchone() is not None:
                raise OrdineManualeIdentityUnavailableError(
                    f"{ordine_id.value} esiste gia': il contatore ORDINE_ID e' indietro "
                    "rispetto agli ordini esistenti."
                )
            cursor.execute(
                """INSERT INTO tpo.ordini
                   (public_id,cliente_id,data_ordine,data_consegna_prevista,stato,
                    tipo_creazione,created_by)
                   VALUES (%s,%s,%s,%s,'APERTO','MANUALE',%s)
                   RETURNING id,created_at,version""",
                (ordine_id.value, client[0], command.data_ordine,
                 command.data_consegna_prevista, actor),
            )
            ordine_pk, recorded_at, version = cursor.fetchone()
            righe: list[RigaOrdineRegistrata] = []
            for position, riga in enumerate(command.righe, 1):
                riga_id = RigaOrdineId(f"RO-{riga_numero + position - 1:06d}")
                cursor.execute(
                    """INSERT INTO tpo.righe_ordine
                       (ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (ordine_pk, position, variety_pks[riga.varieta_id.value],
                     riga.quantita, riga.unita_misura.value, riga_id.value),
                )
                righe.append(RigaOrdineRegistrata(
                    riga_id, position, riga.varieta_id, riga.quantita, riga.unita_misura,
                ))
            after = {
                "public_id": ordine_id.value, "cliente_id": command.client_id.value,
                "data_ordine": command.data_ordine.isoformat(),
                "data_consegna_prevista": (
                    None if command.data_consegna_prevista is None
                    else command.data_consegna_prevista.isoformat()
                ),
                "stato": "APERTO", "tipo_creazione": "MANUALE",
                "righe": [
                    {"public_id": r.riga_id.value, "posizione": r.posizione,
                     "varieta_id": r.varieta_id.value, "quantita": str(r.quantita),
                     "uom": r.unita_misura.value} for r in righe
                ],
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'ORDINE',%s,'INSERT',%s,NULL,%s,%s,%s)""",
                (recorded_at, actor, ordine_id.value, command.authority.reason,
                 Jsonb(after), command.authority.correlation_id,
                 json.dumps({"boundary": "ordine-manuale-v1",
                             "idempotency_key": command.authority.idempotency_key},
                            sort_keys=True)),
            )
            cursor.execute(
                """UPDATE tpo.ordine_manuale_requests
                   SET ordine_id=%s,outcome='COMMITTED'
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (ordine_pk, reservation, command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise OrdineManualeReconciliationRequiredError(
                    "Reservation ORDINE_MANUALE non aggiornabile."
                )
            self._advance(cursor, ORDINE_SEQUENCE, ordine_sequence, 1, actor, recorded_at)
            self._advance(cursor, RIGA_SEQUENCE, riga_sequence, len(command.righe), actor,
                          recorded_at)
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = RegistraOrdineManualeResult(
                ordine_id, command.client_id, "APERTO", int(version), tuple(righe), "INSERTED",
            )
            try:
                connection.commit()
            except Exception as exc:
                raise OrdineManualeCommitOutcomeUncertainError(
                    "Esito commit ORDINE_MANUALE da riconciliare tramite idempotency_key."
                ) from exc
            committed = True
            return result
        except OrdineManualeError:
            raise
        except psycopg.IntegrityError as exc:
            name = getattr(exc.diag, "constraint_name", "") or ""
            if name == "uq_ordine_manuale_request_key":
                raise OrdineManualeReconciliationRequiredError(
                    "Collisione idempotency inattesa da riconciliare."
                ) from exc
            if name.startswith("ck_ordini_") or name.startswith("ordini_"):
                raise OrdineManualePersistenceInvariantError(
                    "Vincolo ORDINE_MANUALE non soddisfatto."
                ) from exc
            raise OrdineManualeCommitRolledBackError(
                "Vincolo ORDINE_MANUALE non soddisfatto."
            ) from exc
        except psycopg.Error as exc:
            raise OrdineManualeCommitRolledBackError(
                "ORDINE_MANUALE fallito con rollback certo."
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
        cursor: Any, command: RegistraOrdineManuale,
    ) -> tuple[int | None, RegistraOrdineManualeResult | None]:
        cursor.execute(
            """INSERT INTO tpo.ordine_manuale_requests
               (idempotency_key,canonical_payload_hash,ordine_id,outcome,recorded_at,created_by)
               VALUES (%s,%s,NULL,'RESERVED',CURRENT_TIMESTAMP,%s)
               ON CONFLICT (idempotency_key) DO NOTHING RETURNING id""",
            (command.authority.idempotency_key, command.canonical_payload_hash,
             command.authority.actor.value),
        )
        row = cursor.fetchone()
        if row is not None:
            return row[0], None
        cursor.execute(
            """SELECT q.canonical_payload_hash,q.outcome,o.id,o.public_id,c.public_id,
                      o.stato::text,o.version
               FROM tpo.ordine_manuale_requests q
               LEFT JOIN tpo.ordini o ON o.id=q.ordine_id
               LEFT JOIN tpo.clienti c ON c.id=o.cliente_id
               WHERE q.idempotency_key=%s FOR UPDATE OF q""",
            (command.authority.idempotency_key,),
        )
        row = cursor.fetchone()
        if row is None:
            raise OrdineManualeReconciliationRequiredError(
                "Reservation ORDINE_MANUALE concorrente non leggibile."
            )
        if row[0] != command.canonical_payload_hash:
            raise OrdineManualeIdempotencyConflictError(
                "Stessa idempotency key con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise OrdineManualeReconciliationRequiredError(
                "Reservation ORDINE_MANUALE priva di risultato committed."
            )
        cursor.execute(
            """SELECT ro.public_id,ro.posizione,v.public_id,ro.quantita,ro.unita_misura::text
               FROM tpo.righe_ordine ro JOIN tpo.varieta v ON v.id=ro.varieta_id
               WHERE ro.ordine_id=%s ORDER BY ro.posizione""",
            (row[2],),
        )
        righe = tuple(
            RigaOrdineRegistrata(
                RigaOrdineId(r[0]), r[1], VarietaId(r[2]), Decimal(r[3]), UnitOfMeasure(r[4]),
            ) for r in cursor.fetchall()
        )
        return None, RegistraOrdineManualeResult(
            OrdineId(row[3]), ClienteId(row[4]), row[5], int(row[6]), righe,
            "COMPATIBLE_REPLAY",
        )

    @staticmethod
    def _allocate(cursor: Any, sequence: tuple[str, str, str], count: int) -> tuple[int, tuple[Any, ...]]:
        cursor.execute(
            """SELECT sequence_name,identifier_type,prefix,next_value,version
               FROM tpo.id_sequences WHERE sequence_name=%s FOR UPDATE""",
            (sequence[0],),
        )
        row = cursor.fetchone()
        if row is None or tuple(row[:3]) != sequence:
            raise OrdineManualeIdentityUnavailableError(
                f"Autorita' {sequence[0]} assente o incompatibile."
            )
        return int(row[3]), row

    @staticmethod
    def _advance(cursor: Any, sequence: tuple[str, str, str], row: tuple[Any, ...],
                 count: int, actor: str, recorded_at: Any) -> None:
        cursor.execute(
            """UPDATE tpo.id_sequences SET next_value=%s,version=version+1,
               updated_at=%s,updated_by=%s WHERE sequence_name=%s
               AND identifier_type=%s AND prefix=%s AND next_value=%s AND version=%s""",
            (row[3] + count, recorded_at, actor, sequence[0], sequence[1], sequence[2],
             row[3], row[4]),
        )
        if cursor.rowcount != 1:
            raise OrdineManualeIdentityUnavailableError(
                f"Conflitto contatore {sequence[0]}."
            )
