"""Adapter PostgreSQL per la persistenza versionata delle RUN."""

from __future__ import annotations

import psycopg

from ...application.run_tracking.errors import (
    InvalidSchedulingRunError,
    SchedulingRunAlreadyExistsError,
    SchedulingRunConflictError,
    SchedulingRunNotFoundError,
)
from ...application.run_tracking.models import CompletedSchedulingRun, OpenSchedulingRun
from ...domain.identifiers import RunId
from ...domain.states import RunState
from ...domain.time_reference import CurrentSystemDate
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError


class PostgreSQLSchedulingRunRepository:
    """Implementa ``SchedulingRunRepository`` sulle tabelle PostgreSQL ufficiali."""

    def __init__(
        self,
        connection_factory: PostgreSQLConnectionFactory,
        *,
        created_by: str = "tpo.scheduling",
    ) -> None:
        if not isinstance(created_by, str) or not created_by.strip():
            raise ValueError("created_by deve essere una stringa non vuota.")
        self._connection_factory = connection_factory
        self._created_by = created_by.strip()

    def add_open_run(self, run: OpenSchedulingRun) -> None:
        if not isinstance(run, OpenSchedulingRun):
            raise InvalidSchedulingRunError("run deve essere una OpenSchedulingRun.")
        connection = self._connection_factory.connect()
        committed = False
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tpo.runs (
                        public_id, started_at, completed_at, simulation, state,
                        programmi_letti, righe_valutate, occorrenze_valutate,
                        ordini_generati, elementi_saltati, version, created_by
                    ) VALUES (%s, %s, NULL, %s, NULL, 0, 0, 0, 0, 0, %s, %s)
                    RETURNING public_id, started_at, completed_at, simulation, state,
                              programmi_letti, righe_valutate, occorrenze_valutate,
                              ordini_generati, elementi_saltati, version
                    """,
                    (
                        run.run_id.value,
                        run.started_at.datetime,
                        run.simulation,
                        run.version,
                        self._created_by,
                    ),
                )
                row = cursor.fetchone()
                if cursor.rowcount != 1 or row is None:
                    raise PostgreSQLError("L'apertura PostgreSQL della RUN non ha inserito una riga.")
                expected = (
                    run.run_id.value,
                    run.started_at.datetime,
                    None,
                    run.simulation,
                    None,
                    0,
                    0,
                    0,
                    0,
                    0,
                    run.version,
                )
                if tuple(row) != expected:
                    raise PostgreSQLError("Il risultato dell'apertura PostgreSQL non è coerente.")
            connection.commit()
            committed = True
        except psycopg.errors.UniqueViolation as exc:
            raise SchedulingRunAlreadyExistsError(run.run_id.value) from exc
        except psycopg.Error as exc:
            raise PostgreSQLError("Apertura della RUN PostgreSQL fallita.") from exc
        finally:
            _cleanup(connection, rollback=not committed)

    def get(self, run_id: RunId) -> OpenSchedulingRun | CompletedSchedulingRun:
        if not isinstance(run_id, RunId):
            raise InvalidSchedulingRunError("run_id deve essere un RunId.")
        connection = self._connection_factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT r.public_id, r.started_at, r.completed_at, r.simulation, r.state,
                           r.programmi_letti, r.righe_valutate, r.occorrenze_valutate,
                           r.ordini_generati, r.elementi_saltati, r.version,
                           ARRAY(
                               SELECT m.messaggio FROM tpo.run_messaggi AS m
                               WHERE m.run_id = r.id AND m.tipo = 'WARNING'
                               ORDER BY m.posizione
                           ) AS warnings,
                           ARRAY(
                               SELECT m.messaggio FROM tpo.run_messaggi AS m
                               WHERE m.run_id = r.id AND m.tipo = 'ERROR'
                               ORDER BY m.posizione
                           ) AS errors
                    FROM tpo.runs AS r
                    WHERE r.public_id = %s
                    """,
                    (run_id.value,),
                )
                row = cursor.fetchone()
            if row is None:
                raise SchedulingRunNotFoundError(run_id.value)
            return _run_from_row(row)
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura della RUN PostgreSQL fallita.") from exc
        finally:
            _cleanup(connection, rollback=True)

    def complete(
        self,
        *,
        run_id: RunId,
        expected_version: int,
        completed_run: CompletedSchedulingRun,
    ) -> bool:
        _validate_completion(run_id, expected_version, completed_run)
        connection = self._connection_factory.connect()
        committed = False
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tpo.runs
                    SET completed_at = %s, state = %s,
                        programmi_letti = %s, righe_valutate = %s,
                        occorrenze_valutate = %s, ordini_generati = %s,
                        elementi_saltati = %s, version = version + 1
                    WHERE public_id = %s AND version = %s
                      AND completed_at IS NULL AND state IS NULL
                    RETURNING id, public_id, started_at, completed_at, simulation, state,
                              programmi_letti, righe_valutate, occorrenze_valutate,
                              ordini_generati, elementi_saltati, version
                    """,
                    (
                        completed_run.completed_at.datetime,
                        completed_run.state.value,
                        completed_run.programmi_letti,
                        completed_run.righe_valutate,
                        completed_run.occorrenze_valutate,
                        completed_run.ordini_generati,
                        completed_run.elementi_saltati,
                        run_id.value,
                        expected_version,
                    ),
                )
                row = cursor.fetchone()
                if cursor.rowcount == 0 or row is None:
                    raise SchedulingRunConflictError(run_id.value)
                if cursor.rowcount != 1:
                    raise PostgreSQLError("Il completamento PostgreSQL ha aggiornato righe inattese.")
                internal_id = row[0]
                expected = (
                    run_id.value,
                    completed_run.started_at.datetime,
                    completed_run.completed_at.datetime,
                    completed_run.simulation,
                    completed_run.state.value,
                    completed_run.programmi_letti,
                    completed_run.righe_valutate,
                    completed_run.occorrenze_valutate,
                    completed_run.ordini_generati,
                    completed_run.elementi_saltati,
                    completed_run.version,
                )
                if tuple(row[1:]) != expected:
                    raise PostgreSQLError("Il risultato del completamento PostgreSQL non è coerente.")
                message_count = len(completed_run.warnings) + len(completed_run.errors)
                if message_count:
                    cursor.execute(
                        """
                        INSERT INTO tpo.run_messaggi (run_id, tipo, posizione, messaggio)
                        SELECT %s, 'WARNING'::tpo.run_message_type, position, message
                        FROM unnest(%s::text[]) WITH ORDINALITY AS warning(message, position)
                        UNION ALL
                        SELECT %s, 'ERROR'::tpo.run_message_type, position, message
                        FROM unnest(%s::text[]) WITH ORDINALITY AS error(message, position)
                        """,
                        (
                            internal_id,
                            list(completed_run.warnings),
                            internal_id,
                            list(completed_run.errors),
                        ),
                    )
                    if cursor.rowcount != message_count:
                        raise PostgreSQLError("Persistenza dei messaggi RUN incompleta.")
            connection.commit()
            committed = True
            return True
        except psycopg.Error as exc:
            raise PostgreSQLError("Completamento della RUN PostgreSQL fallito.") from exc
        finally:
            _cleanup(connection, rollback=not committed)


def _run_from_row(row: tuple[object, ...]) -> OpenSchedulingRun | CompletedSchedulingRun:
    run_id = RunId(row[0])
    started_at = CurrentSystemDate(row[1])
    if row[2] is None and row[4] is None:
        return OpenSchedulingRun(run_id, started_at, row[3], row[10])
    if row[2] is None or row[4] is None:
        raise InvalidSchedulingRunError("Stato persistente della RUN incoerente.")
    return CompletedSchedulingRun(
        run_id=run_id,
        started_at=started_at,
        completed_at=CurrentSystemDate(row[2]),
        simulation=row[3],
        state=RunState(row[4]),
        programmi_letti=row[5],
        righe_valutate=row[6],
        occorrenze_valutate=row[7],
        ordini_generati=row[8],
        elementi_saltati=row[9],
        version=row[10],
        warnings=tuple(row[11]),
        errors=tuple(row[12]),
    )


def _validate_completion(
    run_id: RunId,
    expected_version: int,
    completed_run: CompletedSchedulingRun,
) -> None:
    if not isinstance(run_id, RunId):
        raise InvalidSchedulingRunError("run_id deve essere un RunId.")
    if not isinstance(completed_run, CompletedSchedulingRun):
        raise InvalidSchedulingRunError("completed_run deve essere una CompletedSchedulingRun.")
    if run_id != completed_run.run_id:
        raise InvalidSchedulingRunError("completed_run appartiene a una RUN diversa.")
    if (
        isinstance(expected_version, bool)
        or not isinstance(expected_version, int)
        or expected_version < 0
    ):
        raise InvalidSchedulingRunError("expected_version deve essere un intero non negativo.")
    if completed_run.version != expected_version + 1:
        raise InvalidSchedulingRunError("La versione conclusa deve avanzare di una unità.")


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
