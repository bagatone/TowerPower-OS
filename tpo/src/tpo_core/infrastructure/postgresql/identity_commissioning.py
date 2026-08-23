"""PostgreSQL append-only writer for incremental Identity commissioning."""

from __future__ import annotations

from typing import Any

import psycopg

from ...application.identity.errors import (
    IdentityCommissioningConflictError,
    IdentityCommissioningOutcomeUncertain,
    IdentityCommissioningPersistenceError,
)
from ...application.identity.models import (
    CommissionedIdentityRegistration,
    CommissionIdentityRegistration,
    IdentifierSequence,
)
from .connection import PostgreSQLConnectionFactory


class PostgreSQLIdentityRegistrationCommissioningWriter:
    """Inserisce una registrazione o prova un replay esattamente compatibile."""

    def __init__(self, connection_factory: PostgreSQLConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def commission(
        self, command: CommissionIdentityRegistration,
    ) -> CommissionedIdentityRegistration:
        connection = self._connection_factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            cursor.execute(
                """INSERT INTO tpo.id_sequences
                     (sequence_name,identifier_type,prefix,next_value,version,
                      updated_at,updated_by)
                   VALUES (%s,%s,%s,1,0,CURRENT_TIMESTAMP,%s)
                   ON CONFLICT (sequence_name) DO NOTHING
                   RETURNING sequence_name,identifier_type,prefix,next_value,
                             version,updated_at""",
                (
                    command.sequence_name,
                    command.permanent_id_type.__name__,
                    command.prefix,
                    command.actor.value,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                row = self._load(cursor, command.sequence_name)
                if row is None or not _compatible(command, row):
                    raise IdentityCommissioningConflictError(
                        "La registrazione Identity esiste con autorità differente."
                    )
            result = _result(command, row)
            try:
                connection.commit()
            except Exception as exc:
                raise IdentityCommissioningOutcomeUncertain(
                    "Esito del commit Identity da riconciliare."
                ) from exc
            committed = True
            return result
        except IdentityCommissioningConflictError:
            raise
        except psycopg.IntegrityError as exc:
            raise IdentityCommissioningConflictError(
                "Vincolo della registrazione Identity non soddisfatto."
            ) from exc
        except psycopg.Error as exc:
            raise IdentityCommissioningPersistenceError(
                "Commissioning Identity non completato con rollback certo."
            ) from exc
        finally:
            _cleanup(cursor, connection, rollback=not committed)

    @staticmethod
    def _load(cursor: Any, sequence_name: str) -> tuple[Any, ...] | None:
        cursor.execute(
            """SELECT sequence_name,identifier_type,prefix,next_value,version,
                      updated_at
               FROM tpo.id_sequences
               WHERE sequence_name=%s""",
            (sequence_name,),
        )
        return cursor.fetchone()


def _compatible(
    command: CommissionIdentityRegistration, row: tuple[Any, ...],
) -> bool:
    return (
        row[0] == command.sequence_name
        and row[1] == command.permanent_id_type.__name__
        and row[2] == command.prefix
    )


def _result(
    command: CommissionIdentityRegistration, row: tuple[Any, ...],
) -> CommissionedIdentityRegistration:
    return CommissionedIdentityRegistration(
        command=command,
        sequence=IdentifierSequence(row[1], row[2], row[3], row[4]),
        commissioned_at=row[5],
    )


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
