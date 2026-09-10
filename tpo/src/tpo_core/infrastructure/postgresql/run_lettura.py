"""Reader PostgreSQL a sola lettura per RUN/RUN_LOG V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md.
Legge tpo.runs, tpo.run_messaggi e tpo.run_log. Nessuna scrittura.
"""
from __future__ import annotations

import json
from collections import defaultdict

import psycopg

from ...application.run_lettura.errors import RunLetturaRunNotFoundError
from ...application.run_lettura.models import (
    ElencoRun, RichiediElencoRun, RichiediRunLog, Run, RunLog, RunLogVoce, RunMessaggio,
)
from ...domain.identifiers import RunId
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError

_SELECT_RUNS = (
    "SELECT public_id, started_at, completed_at, simulation, state, programmi_letti, "
    "righe_valutate, occorrenze_valutate, ordini_generati, elementi_saltati FROM tpo.runs"
)
_SELECT_MESSAGGI = (
    "SELECT r.public_id, m.tipo, m.posizione, m.messaggio, m.created_at "
    "FROM tpo.run_messaggi m JOIN tpo.runs r ON r.id = m.run_id"
)
_SELECT_LOG = (
    "SELECT l.occurred_at, l.level, l.event_type, l.message, l.context "
    "FROM tpo.run_log l JOIN tpo.runs r ON r.id = l.run_id"
)


def _context_as_mapping(value):
    if isinstance(value, dict):
        return value
    return json.loads(value)


class PostgreSQLRunLetturaReader:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def elenco(self, query: RichiediElencoRun) -> ElencoRun:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_RUNS} ORDER BY started_at DESC")
                run_rows = cursor.fetchall()
                cursor.execute(f"{_SELECT_MESSAGGI} ORDER BY m.posizione")
                messaggi_rows = cursor.fetchall()
            messaggi_per_run: dict[str, list[RunMessaggio]] = defaultdict(list)
            for run_public_id, tipo, posizione, messaggio, created_at in messaggi_rows:
                messaggi_per_run[run_public_id].append(
                    RunMessaggio(tipo, posizione, messaggio, created_at)
                )
            runs = tuple(
                Run(
                    RunId(public_id), started_at, completed_at, simulation, state,
                    programmi_letti, righe_valutate, occorrenze_valutate, ordini_generati,
                    elementi_saltati, tuple(messaggi_per_run.get(public_id, [])),
                )
                for (public_id, started_at, completed_at, simulation, state, programmi_letti,
                     righe_valutate, occorrenze_valutate, ordini_generati,
                     elementi_saltati) in run_rows
            )
            return ElencoRun(runs)
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura RUN PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def log(self, query: RichiediRunLog) -> RunLog:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM tpo.runs WHERE public_id=%s", (query.run_id.value,)
                )
                if cursor.fetchone() is None:
                    raise RunLetturaRunNotFoundError("RUN inesistente.")
                cursor.execute(
                    f"{_SELECT_LOG} WHERE r.public_id=%s ORDER BY l.occurred_at",
                    (query.run_id.value,),
                )
                rows = cursor.fetchall()
            voci = tuple(
                RunLogVoce(occurred_at, level, event_type, message, _context_as_mapping(context))
                for (occurred_at, level, event_type, message, context) in rows
            )
            return RunLog(query.run_id, voci)
        except RunLetturaRunNotFoundError:
            raise
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura RUN_LOG PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    @staticmethod
    def _release(connection) -> None:
        try:
            connection.rollback()
        except Exception:
            pass
        try:
            connection.close()
        except Exception:
            pass
