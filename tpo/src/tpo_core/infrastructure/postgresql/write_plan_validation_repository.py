"""Snapshot PostgreSQL read-only per la validazione del Write Plan."""

from __future__ import annotations

import psycopg

from ...application.write_plan.errors import WriteTargetMismatchError
from ...application.write_plan.models import WriteTargetSnapshot
from ...application.write_plan.validation import (
    WRITE_SCHEMA_ORDINI,
    WRITE_SCHEMA_VERSION,
    WRITE_TARGET_ORDINI,
)
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError


class PostgreSQLWritePlanValidationRepository:
    """Legge esclusivamente le chiavi idempotenti del target ORDINI."""

    def __init__(self, connection_factory: PostgreSQLConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def get_target_snapshot(self, *, target_name: str) -> WriteTargetSnapshot:
        if target_name != WRITE_TARGET_ORDINI:
            raise WriteTargetMismatchError("Il target PostgreSQL richiesto non è supportato.")
        connection = self._connection_factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT chiave_idempotenza
                    FROM tpo.ordini
                    WHERE chiave_idempotenza IS NOT NULL
                    ORDER BY chiave_idempotenza
                    """,
                    (),
                )
                keys = tuple(row[0] for row in cursor.fetchall())
            return WriteTargetSnapshot(
                target_name=WRITE_TARGET_ORDINI,
                schema_name=WRITE_SCHEMA_ORDINI,
                schema_version=WRITE_SCHEMA_VERSION,
                existing_idempotency_keys=keys,
            )
        except psycopg.Error as exc:
            raise PostgreSQLError(
                "Lettura dello snapshot ORDINI PostgreSQL fallita."
            ) from exc
        finally:
            _cleanup(connection)


def _cleanup(connection: object) -> None:
    try:
        connection.rollback()
    except Exception:
        pass
    try:
        connection.close()
    except Exception:
        pass
