"""Adapter PostgreSQL per le sequenze persistenti degli identificativi."""

from __future__ import annotations

from typing import TypeVar

import psycopg

from ...application.identity.errors import (
    IdentifierSequenceConflictError,
    IdentifierSequenceNotFoundError,
    InvalidIdentifierSequenceError,
)
from ...application.identity.models import IdentifierSequence
from ...domain.identifiers import PermanentId
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError


IdentifierT = TypeVar("IdentifierT", bound=PermanentId)


class PostgreSQLPersistentIdRepository:
    """Implementa la porta Identity usando ``tpo.id_sequences`` come autorità."""

    def __init__(
        self,
        connection_factory: PostgreSQLConnectionFactory,
        *,
        updated_by: str = "tpo.identity",
    ) -> None:
        if not isinstance(updated_by, str) or not updated_by.strip():
            raise ValueError("updated_by deve essere una stringa non vuota.")
        self._connection_factory = connection_factory
        self._updated_by = updated_by.strip()

    def get_sequence(self, identifier_type: type[IdentifierT]) -> IdentifierSequence:
        """Legge lo snapshot necessario al compare-and-set applicativo."""
        connection = self._connection_factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT identifier_type, prefix, next_value, version
                    FROM tpo.id_sequences
                    WHERE identifier_type = %s
                    """,
                    (identifier_type.__name__,),
                )
                row = cursor.fetchone()
            if row is None:
                raise IdentifierSequenceNotFoundError(identifier_type.__name__)
            sequence = _sequence(row)
            if sequence.prefix != identifier_type.prefix:
                raise InvalidIdentifierSequenceError("prefix della sequenza non coerente.")
            return sequence
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura della sequenza PostgreSQL fallita.") from exc
        finally:
            _cleanup(connection, rollback=True)

    def compare_and_set(
        self,
        *,
        identifier_type: type[IdentifierT],
        expected_version: int,
        expected_next_value: int,
        new_next_value: int,
    ) -> bool:
        """Avanza atomicamente la sequenza con una sola UPDATE condizionale."""
        _validate_cas_input(
            identifier_type=identifier_type,
            expected_version=expected_version,
            expected_next_value=expected_next_value,
            new_next_value=new_next_value,
        )
        connection = self._connection_factory.connect()
        committed = False
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tpo.id_sequences
                    SET next_value = %s,
                        version = version + 1,
                        updated_at = CURRENT_TIMESTAMP,
                        updated_by = %s
                    WHERE identifier_type = %s
                      AND prefix = %s
                      AND version = %s
                      AND next_value = %s
                    RETURNING identifier_type, prefix, next_value, version
                    """,
                    (
                        new_next_value,
                        self._updated_by,
                        identifier_type.__name__,
                        identifier_type.prefix,
                        expected_version,
                        expected_next_value,
                    ),
                )
                row = cursor.fetchone()
                if cursor.rowcount == 0 or row is None:
                    raise IdentifierSequenceConflictError(
                        f"Conflitto durante l'allocazione di {identifier_type.__name__}."
                    )
                if cursor.rowcount != 1:
                    raise PostgreSQLError(
                        "Il CAS PostgreSQL ha aggiornato un numero inatteso di righe."
                    )
                expected_row = (
                    identifier_type.__name__,
                    identifier_type.prefix,
                    new_next_value,
                    expected_version + 1,
                )
                if tuple(row) != expected_row:
                    raise PostgreSQLError("Il risultato del CAS PostgreSQL non è coerente.")
            connection.commit()
            committed = True
            return True
        except psycopg.Error as exc:
            raise PostgreSQLError("Aggiornamento della sequenza PostgreSQL fallito.") from exc
        finally:
            _cleanup(connection, rollback=not committed)


def _sequence(row: tuple[object, ...]) -> IdentifierSequence:
    return IdentifierSequence(
        identifier_type=row[0],
        prefix=row[1],
        next_value=row[2],
        version=row[3],
    )


def _validate_cas_input(
    *,
    identifier_type: type[IdentifierT],
    expected_version: int,
    expected_next_value: int,
    new_next_value: int,
) -> None:
    if (
        not isinstance(identifier_type, type)
        or not issubclass(identifier_type, PermanentId)
        or identifier_type is PermanentId
    ):
        raise InvalidIdentifierSequenceError(
            "È richiesto un sottotipo concreto di PermanentId."
        )
    if (
        isinstance(expected_version, bool)
        or not isinstance(expected_version, int)
        or expected_version < 0
    ):
        raise InvalidIdentifierSequenceError("expected_version deve essere un intero non negativo.")
    if (
        isinstance(expected_next_value, bool)
        or not isinstance(expected_next_value, int)
        or expected_next_value <= 0
    ):
        raise InvalidIdentifierSequenceError("expected_next_value deve essere un intero positivo.")
    if (
        isinstance(new_next_value, bool)
        or not isinstance(new_next_value, int)
        or new_next_value != expected_next_value + 1
    ):
        raise InvalidIdentifierSequenceError(
            "new_next_value deve avanzare expected_next_value di una unità."
        )


def _cleanup(connection: object, *, rollback: bool) -> None:
    if rollback:
        try:
            connection.rollback()
        except Exception:
            pass
    try:
        connection.close()
    except Exception:
        pass
