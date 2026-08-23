"""Atomic PostgreSQL commissioning of missing order-line permanent identities."""

from __future__ import annotations

import json
from typing import Any

import psycopg

from ...application.order_line_identity import (
    CommissionExistingOrderLineIdentities, ExistingOrderLineIdentityResult,
)
from ...domain.identifiers import RigaOrdineId
from .connection import PostgreSQLConnectionFactory


class PostgreSQLExistingOrderLineIdentityWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def commission(self, command: CommissionExistingOrderLineIdentities) -> ExistingOrderLineIdentityResult:
        connection = self._factory.connect(); cursor = None; committed = False
        try:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT ro.id,o.public_id,ro.posizione,ro.public_id,ro.varieta_id,
                          ro.quantita,ro.unita_misura,ro.version
                   FROM tpo.righe_ordine ro JOIN tpo.ordini o ON o.id=ro.ordine_id
                   ORDER BY o.public_id,ro.posizione,ro.id FOR UPDATE OF ro"""
            )
            rows = cursor.fetchall()
            if len(rows) != command.expected_count:
                raise ValueError("Numero righe ordine differente dall'autorità attesa.")
            identified = [row for row in rows if row[3] is not None]
            nulls = [row for row in rows if row[3] is None]
            if identified and nulls:
                raise ValueError("Commissioning parziale/conflicting rilevato.")
            cursor.execute(
                """SELECT sequence_name,identifier_type,prefix,next_value,version
                   FROM tpo.id_sequences WHERE sequence_name=%s FOR UPDATE""",
                (RigaOrdineId.sequence_name,),
            )
            sequence = cursor.fetchone()
            if sequence is None or sequence[:3] != (
                RigaOrdineId.sequence_name, RigaOrdineId.__name__, RigaOrdineId.prefix,
            ):
                raise ValueError("Autorità RIGA_ORDINE_ID assente o incoerente.")
            if identified:
                expected = [f"RO-{i:06d}" for i in range(1, len(rows) + 1)]
                if [row[3] for row in rows] != expected:
                    raise ValueError("Identità esistenti incompatibili con il replay canonico.")
                return ExistingOrderLineIdentityResult(0, len(rows))
            start = sequence[3]
            for offset, row in enumerate(rows):
                public_id = RigaOrdineId(f"RO-{start + offset:06d}")
                correlation = f"{command.correlation_prefix}:{row[1]}:{row[2]}"
                before = {"public_id": None, "order_public_id": row[1], "position": row[2]}
                after = {**before, "public_id": public_id.value}
                cursor.execute(
                    "UPDATE tpo.righe_ordine SET public_id=%s WHERE id=%s AND public_id IS NULL",
                    (public_id.value, row[0]),
                )
                if cursor.rowcount != 1:
                    raise ValueError("Conflitto commissioning RIGA_ORDINE.")
                cursor.execute(
                    """INSERT INTO tpo.audit_eventi
                       (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                        before_data,after_data,correlation_id,provenance)
                       VALUES (CURRENT_TIMESTAMP,%s,'RIGA_ORDINE',%s,'STATE_TRANSITION',
                               %s,%s::jsonb,%s::jsonb,%s,'order-line-identity-commissioning')""",
                    (command.actor.value, public_id.value, command.reason,
                     json.dumps(before, sort_keys=True), json.dumps(after, sort_keys=True), correlation),
                )
            cursor.execute(
                """UPDATE tpo.id_sequences SET next_value=%s,version=version+%s,
                          updated_at=CURRENT_TIMESTAMP,updated_by=%s
                   WHERE sequence_name=%s AND next_value=%s AND version=%s""",
                (start + len(rows), len(rows), command.actor.value,
                 RigaOrdineId.sequence_name, start, sequence[4]),
            )
            if cursor.rowcount != 1:
                raise ValueError("Conflitto counter RIGA_ORDINE_ID.")
            connection.commit(); committed = True
            return ExistingOrderLineIdentityResult(len(rows), 0)
        except psycopg.Error as exc:
            raise RuntimeError("Commissioning RIGA_ORDINE PostgreSQL fallito.") from exc
        finally:
            if not committed:
                try: connection.rollback()
                except Exception: pass
            if cursor is not None: cursor.close()
            connection.close()
