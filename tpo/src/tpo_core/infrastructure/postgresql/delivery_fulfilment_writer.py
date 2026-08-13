"""Writer PostgreSQL autorevole del Delivery Fulfilment V1."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.delivery_fulfilment.errors import (
    DeliveryAlreadyPublishedError,
    DeliveryCommitError,
    DeliveryCommitOutcomeUncertain,
    DeliveryConcurrencyError,
    DeliveryValidationError,
    InvalidDeliveryCommandError,
)
from ...application.delivery_fulfilment.models import (
    DeliveryFulfilmentCommand,
    DeliveryFulfilmentLine,
    DeliveryFulfilmentResult,
)
from ...application.ports.clock import Clock
from ...domain.identifiers import OrdineId
from .connection import PostgreSQLConnectionFactory


class PostgreSQLDeliveryFulfilmentWriter:
    """Possiede l'intero transaction boundary commerciale e fisico."""

    def __init__(
        self, connection_factory: PostgreSQLConnectionFactory, clock: Clock
    ) -> None:
        self._connection_factory = connection_factory
        self._clock = clock

    def publish(self, command: DeliveryFulfilmentCommand) -> DeliveryFulfilmentResult:
        if not isinstance(command, DeliveryFulfilmentCommand):
            raise InvalidDeliveryCommandError("command non valido.")
        correction = command.is_correction
        connection = self._connection_factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            persistence_at = self._clock.now().datetime
            result = self._execute(
                cursor, command, correction=correction,
                persistence_at=persistence_at,
            )
            try:
                connection.commit()
            except Exception as exc:
                raise DeliveryCommitOutcomeUncertain(
                    "Esito del commit Delivery Fulfilment da riconciliare tramite CONSEGNA."
                ) from exc
            committed = True
            return result
        except (DeliveryAlreadyPublishedError, DeliveryConcurrencyError, DeliveryValidationError):
            raise
        except psycopg.errors.UniqueViolation as exc:
            if getattr(exc.diag, "constraint_name", None) == "consegne_public_id_key":
                raise DeliveryAlreadyPublishedError(
                    "La CONSEGNA risulta già pubblicata."
                ) from exc
            raise DeliveryValidationError("Vincolo univoco Delivery Fulfilment violato.") from exc
        except (psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected) as exc:
            raise DeliveryConcurrencyError("Conflitto concorrente Delivery Fulfilment.") from exc
        except psycopg.IntegrityError as exc:
            raise DeliveryValidationError("Vincolo Delivery Fulfilment violato.") from exc
        except psycopg.Error as exc:
            raise DeliveryCommitError(
                "Delivery Fulfilment non completato con rollback certo."
            ) from exc
        finally:
            _cleanup(cursor, connection, rollback=not committed)

    def _execute(
        self, cursor: Any, command: DeliveryFulfilmentCommand, *, correction: bool,
        persistence_at: datetime,
    ) -> DeliveryFulfilmentResult:
        cursor.execute(
            "SELECT 1 FROM tpo.consegne WHERE public_id=%s",
            (command.delivery_id.value,),
        )
        if cursor.fetchone() is not None:
            raise DeliveryAlreadyPublishedError("La CONSEGNA risulta già pubblicata.")
        order_ids = sorted({line.order_id.value for line in command.lines})
        cursor.execute(
            """SELECT id,public_id,cliente_id,stato,version
               FROM tpo.ordini WHERE public_id = ANY(%s)
               ORDER BY id FOR UPDATE""",
            (order_ids,),
        )
        order_rows = cursor.fetchall()
        if len(order_rows) != len(order_ids):
            raise DeliveryValidationError("Uno o più ORDINI non esistono.")
        orders = {row[1]: row for row in order_rows}
        expected_order_versions: dict[str, int] = {}
        for line in command.lines:
            previous = expected_order_versions.setdefault(
                line.order_id.value, line.expected_order_version
            )
            if previous != line.expected_order_version:
                raise InvalidDeliveryCommandError(
                    "expected_order_version incoerente per lo stesso ORDINE."
                )
        for public_id, row in orders.items():
            if row[3] == "ANNULLATO":
                raise DeliveryValidationError("Un ORDINE ANNULLATO non accetta fulfilment.")
            if row[4] != expected_order_versions[public_id]:
                raise DeliveryConcurrencyError("Versione ORDINE in conflitto.")

        cursor.execute(
            "SELECT id FROM tpo.clienti WHERE public_id=%s",
            (command.client_id.value,),
        )
        client = cursor.fetchone()
        if client is None:
            raise DeliveryValidationError("CLIENTE assente.")
        client_pk = client[0]
        if any(row[2] != client_pk for row in order_rows):
            raise DeliveryValidationError("Gli ORDINI non appartengono allo stesso CLIENTE.")

        line_ids = sorted(line.order_line_id for line in command.lines)
        cursor.execute(
            """SELECT ro.id,ro.public_id,ro.ordine_id,ro.varieta_id,ro.quantita,
                      ro.unita_misura,ro.version,v.public_id
               FROM tpo.righe_ordine ro
               JOIN tpo.varieta v ON v.id=ro.varieta_id
               WHERE ro.public_id = ANY(%s)
               ORDER BY ro.id FOR UPDATE""",
            (line_ids,),
        )
        rows = cursor.fetchall()
        if len(rows) != len(line_ids):
            raise DeliveryValidationError("Una o più RIGHE_ORDINE non esistono.")
        order_lines = {row[1]: row for row in rows}
        for line in command.lines:
            row = order_lines[line.order_line_id]
            if row[2] != orders[line.order_id.value][0]:
                raise DeliveryValidationError("RIGA_ORDINE non appartenente all'ORDINE.")
            if row[5] != line.unit.value:
                raise DeliveryValidationError("UOM della RIGA_ORDINE non coincidente.")
            if row[6] != line.expected_order_line_version:
                raise DeliveryConcurrencyError("Versione RIGA_ORDINE in conflitto.")

        originals: dict[str, int] = {}
        if correction:
            originals = self._load_originals(cursor, command.lines, order_lines)

        stock: dict[int, list[Any]] = {}
        if not correction:
            variety_pks = sorted({order_lines[line.order_line_id][3] for line in command.lines})
            cursor.execute(
                """SELECT varieta_id,disponibile,unita_misura,version
                   FROM tpo.stock WHERE varieta_id = ANY(%s)
                   ORDER BY varieta_id FOR UPDATE""",
                (variety_pks,),
            )
            stock_rows = cursor.fetchall()
            stock = {row[0]: [Decimal(row[1]), row[2], row[3]] for row in stock_rows}
            if set(stock) != set(variety_pks):
                raise DeliveryValidationError("STOCK richiesto non inizializzato.")
            for line in command.lines:
                row = order_lines[line.order_line_id]
                if stock[row[3]][1] != line.unit.value:
                    raise DeliveryValidationError("UOM STOCK non coincidente.")
                stock[row[3]][0] -= line.quantity
                if stock[row[3]][0] < 0:
                    raise DeliveryValidationError("STOCK insufficiente.")

        delivered = self._delivered(cursor, tuple(order_lines.values()))
        for line in command.lines:
            row = order_lines[line.order_line_id]
            total = delivered[row[0]] + line.quantity
            if total < 0 or total > Decimal(row[4]):
                raise DeliveryValidationError("Fulfilment finale fuori dai limiti dell'ORDINE.")

        cursor.execute(
            """INSERT INTO tpo.consegne
               (public_id,cliente_id,stato,data_prevista,data_effettiva,operatore,
                destinazione_fisica,created_at,created_by)
               VALUES (%s,%s,'CONSEGNATA',%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (
                command.delivery_id.value, client_pk, command.planned_date,
                command.effective_at, command.operator, command.physical_destination,
                persistence_at, command.actor.value,
            ),
        )
        delivery_pk = _returned_id(cursor, "CONSEGNA")

        order_positions = {public_id: position for position, public_id in enumerate(order_ids, 1)}
        for public_id in order_ids:
            cursor.execute(
                "INSERT INTO tpo.consegne_ordini(consegna_id,ordine_id,posizione) VALUES (%s,%s,%s)",
                (delivery_pk, orders[public_id][0], order_positions[public_id]),
            )

        movement_count = 0
        for position, line in enumerate(command.lines, 1):
            row = order_lines[line.order_line_id]
            original_key = f"{line.correction_of.delivery_id.value}:{line.correction_of.position}" if line.correction_of else ""
            cursor.execute(
                """INSERT INTO tpo.righe_consegna
                   (consegna_id,ordine_id,riga_ordine_id,posizione,varieta_id,quantita,
                    unita_misura,rettifica_riga_consegna_id,created_at,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (
                    delivery_pk, row[2], row[0], position, row[3], line.quantity,
                    line.unit.value, originals.get(original_key), persistence_at,
                    command.actor.value,
                ),
            )
            delivery_line_pk = _returned_id(cursor, "RIGA_CONSEGNA")
            if not correction:
                cursor.execute(
                    """INSERT INTO tpo.movimenti_magazzino
                       (public_id,varieta_id,unita_misura,tipo,direzione,quantita,
                        data_movimento,motivo,origine_tipo,origine_riferimento,
                        consegna_id,riga_consegna_id,created_at,created_by)
                       VALUES (%s,%s,%s,'SCARICO','NEGATIVO',%s,%s,%s,'CONSEGNA',
                               %s,%s,%s,%s,%s) RETURNING id""",
                    (
                        line.movement_id.value, row[3], line.unit.value, line.quantity,
                        command.effective_at, command.reason, command.delivery_id.value,
                        delivery_pk, delivery_line_pk, persistence_at,
                        command.actor.value,
                    ),
                )
                movement_pk = _returned_id(cursor, "MOVIMENTO_MAGAZZINO")
                cursor.execute(
                    """UPDATE tpo.stock SET disponibile=disponibile-%s,
                              ultimo_movimento_id=%s,updated_at=%s,version=version+1
                       WHERE varieta_id=%s AND unita_misura=%s
                         AND disponibile >= %s""",
                    (
                        line.quantity, movement_pk, persistence_at, row[3],
                        line.unit.value, line.quantity,
                    ),
                )
                if cursor.rowcount != 1:
                    raise DeliveryConcurrencyError("STOCK cambiato durante il fulfilment.")
                movement_count += 1
            self._audit_line(
                cursor, command, line, position, row[7], persistence_at
            )

        for row in rows:
            cursor.execute(
                "UPDATE tpo.righe_ordine SET version=version+1 WHERE id=%s AND version=%s",
                (row[0], row[6]),
            )
            if cursor.rowcount != 1:
                raise DeliveryConcurrencyError("Aggiornamento RIGA_ORDINE in conflitto.")

        final_states: list[tuple[OrdineId, str]] = []
        for public_id in order_ids:
            order_pk = orders[public_id][0]
            state = self._order_state(cursor, order_pk)
            before_state = orders[public_id][3]
            cursor.execute(
                """UPDATE tpo.ordini SET stato=%s,version=version+1
                   WHERE id=%s AND version=%s""",
                (state, order_pk, expected_order_versions[public_id]),
            )
            if cursor.rowcount != 1:
                raise DeliveryConcurrencyError("Aggiornamento ORDINE in conflitto.")
            self._audit_order(cursor, command, public_id, before_state, state,
                              expected_order_versions[public_id], persistence_at)
            final_states.append((OrdineId(public_id), state))

        self._audit_delivery(
            cursor, command, correction, movement_count, persistence_at
        )
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        return DeliveryFulfilmentResult(
            delivery_id=command.delivery_id,
            order_states=tuple(final_states),
            delivery_line_count=len(command.lines),
            movement_count=movement_count,
        )

    @staticmethod
    def _load_originals(cursor: Any, lines: tuple[DeliveryFulfilmentLine, ...], order_lines: dict[str, tuple[Any, ...]]) -> dict[str, int]:
        result: dict[str, int] = {}
        for line in lines:
            reference = line.correction_of
            assert reference is not None
            cursor.execute(
                """SELECT rc.id,rc.riga_ordine_id,rc.varieta_id,rc.unita_misura,
                          rc.rettifica_riga_consegna_id,c.stato
                   FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id
                   WHERE c.public_id=%s AND rc.posizione=%s""",
                (reference.delivery_id.value, reference.position),
            )
            original = cursor.fetchone()
            current = order_lines[line.order_line_id]
            if (
                original is None or original[4] is not None or original[5] != "CONSEGNATA"
                or original[1] != current[0] or original[2] != current[3]
                or original[3] != line.unit.value
            ):
                raise DeliveryValidationError("Rettifica non riferita a una riga ordinaria coerente.")
            result[f"{reference.delivery_id.value}:{reference.position}"] = original[0]
        return result

    @staticmethod
    def _delivered(cursor: Any, rows: tuple[tuple[Any, ...], ...]) -> dict[int, Decimal]:
        ids = [row[0] for row in rows]
        cursor.execute(
            """SELECT ro.id,COALESCE(SUM(rc.quantita) FILTER
                         (WHERE c.stato='CONSEGNATA'),0)::numeric(20,6)
               FROM tpo.righe_ordine ro
               LEFT JOIN tpo.righe_consegna rc ON rc.riga_ordine_id=ro.id
               LEFT JOIN tpo.consegne c ON c.id=rc.consegna_id
               WHERE ro.id = ANY(%s) GROUP BY ro.id ORDER BY ro.id""",
            (ids,),
        )
        return {row[0]: Decimal(row[1]) for row in cursor.fetchall()}

    @staticmethod
    def _order_state(cursor: Any, order_pk: int) -> str:
        cursor.execute(
            """SELECT count(*),count(*) FILTER (WHERE delivered=0),
                      count(*) FILTER (WHERE delivered=ordered)
               FROM (SELECT ro.id,ro.quantita ordered,
                       COALESCE(SUM(rc.quantita) FILTER
                         (WHERE c.stato='CONSEGNATA'),0) delivered
                     FROM tpo.righe_ordine ro
                     LEFT JOIN tpo.righe_consegna rc ON rc.riga_ordine_id=ro.id
                     LEFT JOIN tpo.consegne c ON c.id=rc.consegna_id
                     WHERE ro.ordine_id=%s GROUP BY ro.id,ro.quantita) totals""",
            (order_pk,),
        )
        count, zero, full = cursor.fetchone()
        if count <= 0:
            raise DeliveryValidationError("ORDINE privo di righe.")
        if zero == count:
            return "APERTO"
        if full == count:
            return "EVASO"
        return "PARZIALMENTE_EVASO"

    @staticmethod
    def _audit(cursor: Any, command: DeliveryFulfilmentCommand, entity_type: str,
               entity_public_id: str, operation: str, before: dict[str, Any] | None,
               after: dict[str, Any] | None, persistence_at: datetime) -> None:
        cursor.execute(
            """INSERT INTO tpo.audit_eventi
               (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                before_data,after_data,correlation_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                persistence_at, command.actor.value, entity_type,
                entity_public_id, operation, command.reason,
                Jsonb(before) if before is not None else None,
                Jsonb(after) if after is not None else None,
                command.correlation_id,
            ),
        )

    @classmethod
    def _audit_line(cls, cursor: Any, command: DeliveryFulfilmentCommand,
                    line: DeliveryFulfilmentLine, position: int,
                    variety_public_id: str, persistence_at: datetime) -> None:
        after = {
            "delivery_public_id": command.delivery_id.value,
            "position": position,
            "order_public_id": line.order_id.value,
            "order_line_public_id": line.order_line_id,
            "variety_public_id": variety_public_id,
            "quantity": str(line.quantity),
            "unit_of_measure": line.unit.value,
            "order_version_before": line.expected_order_version,
            "order_version_after": line.expected_order_version + 1,
            "order_line_version_before": line.expected_order_line_version,
            "order_line_version_after": line.expected_order_line_version + 1,
            "correction_of": None if line.correction_of is None else {
                "delivery_public_id": line.correction_of.delivery_id.value,
                "position": line.correction_of.position,
            },
            "movement_public_id": None if line.movement_id is None else line.movement_id.value,
        }
        cls._audit(cursor, command, "RIGA_CONSEGNA", command.delivery_id.value,
                   "CORRECTION" if line.is_correction else "INSERT", None, after,
                   persistence_at)

    @classmethod
    def _audit_order(cls, cursor: Any, command: DeliveryFulfilmentCommand,
                     public_id: str, before_state: str, after_state: str,
                     version: int, persistence_at: datetime) -> None:
        before = {"public_id": public_id, "state": before_state, "version": version}
        after = {"public_id": public_id, "state": after_state, "version": version + 1}
        cls._audit(
            cursor, command, "ORDINE", public_id,
            "STATE_TRANSITION" if before_state != after_state else "UPDATE",
            before, after, persistence_at,
        )

    @classmethod
    def _audit_delivery(cls, cursor: Any, command: DeliveryFulfilmentCommand,
                        correction: bool, movement_count: int,
                        persistence_at: datetime) -> None:
        cls._audit(cursor, command, "CONSEGNA", command.delivery_id.value,
                   "CORRECTION" if correction else "INSERT", None, {
                       "public_id": command.delivery_id.value,
                       "state": "CONSEGNATA",
                       "effective_at": command.effective_at.isoformat(),
                       "line_count": len(command.lines),
                       "movement_count": movement_count,
                   }, persistence_at)


def _returned_id(cursor: Any, entity: str) -> int:
    row = cursor.fetchone()
    if cursor.rowcount != 1 or row is None or not isinstance(row[0], int) or row[0] <= 0:
        raise DeliveryCommitError(f"RETURNING {entity} incoerente.")
    return row[0]


def _cleanup(cursor: Any, connection: Any, *, rollback: bool) -> None:
    if rollback:
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
