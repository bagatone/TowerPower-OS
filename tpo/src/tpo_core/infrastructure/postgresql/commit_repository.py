"""Writer PostgreSQL atomico del piano ORDINI validato."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.committer.context import CommitExecutionContext
from ...application.committer.errors import (
    CommitExecutionError,
    CommitExistingKeyError,
    CommitPreparationError,
    InvalidCommitRequestError,
)
from ...application.committer.models import CommitExecutionReceipt, CommitRequest
from ...application.run_tracking.models import SchedulingRunCompletion
from ...application.write_plan.models import ValidatedWritePlan
from ...domain.states import OrdineCreationType, RunState
from ...domain.time_reference import CurrentSystemDate
from .connection import PostgreSQLConnectionFactory


class PostgreSQLCommitRepository:
    """Applica l'intero WritePlan in una sola transazione PostgreSQL."""

    def __init__(self, connection_factory: PostgreSQLConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def prepare_commit(self, request: CommitRequest) -> None:
        self._validate(request)

    def execute_commit(
        self, request: CommitRequest, completed_at: CurrentSystemDate
    ) -> CommitExecutionReceipt:
        self._validate(request)
        if not isinstance(completed_at, CurrentSystemDate):
            raise InvalidCommitRequestError("completed_at deve essere CURRENT_SYSTEM_DATE.")
        if completed_at.datetime < request.requested_at.datetime:
            raise InvalidCommitRequestError("completed_at non può precedere requested_at.")

        connection = self._connection_factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            receipt = self._execute(cursor, request, completed_at)
            connection.commit()
            committed = True
            return receipt
        except CommitExistingKeyError:
            raise
        except psycopg.errors.UniqueViolation as exc:
            if (
                getattr(exc.diag, "constraint_name", None)
                == "ordini_chiave_idempotenza_key"
            ):
                raise CommitExistingKeyError(
                    "Una chiave idempotente del piano è già presente nel target."
                ) from exc
            raise CommitExecutionError("Vincolo univoco PostgreSQL violato.") from exc
        except psycopg.Error as exc:
            raise CommitExecutionError("Commit PostgreSQL non completato con esito certo.") from exc
        finally:
            _cleanup(cursor, connection, rollback=not committed)

    @staticmethod
    def _validate(request: CommitRequest) -> None:
        if not isinstance(request, CommitRequest):
            raise InvalidCommitRequestError("request deve essere una CommitRequest valida.")
        if not isinstance(request.validated_plan, ValidatedWritePlan):
            raise InvalidCommitRequestError("validated_plan non valido.")
        if not isinstance(request.execution_context, CommitExecutionContext):
            raise InvalidCommitRequestError("execution_context non valido.")
        completion = request.completion
        if not isinstance(completion, SchedulingRunCompletion) or request.expected_version is None:
            raise CommitPreparationError("Il commit PostgreSQL richiede una completion versionata.")
        plan = request.validated_plan.plan
        if completion.simulation or completion.final_state is RunState.FAILED:
            raise CommitPreparationError("Una RUN simulata o FAILED non può persistere ORDINI.")
        if plan.run_id != completion.run_id or not plan.records:
            raise CommitPreparationError("RUN o record del piano non coerenti.")
        if request.validated_plan.target_name != "ORDINI":
            raise CommitPreparationError("Il piano validato non è destinato a ORDINI.")
        if tuple(r.chiave_idempotenza for r in plan.records) != plan.idempotency_keys:
            raise CommitPreparationError("Chiavi idempotenti non coerenti.")
        if len(set(plan.idempotency_keys)) != len(plan.idempotency_keys):
            raise CommitPreparationError("Chiavi idempotenti duplicate.")
        for record in plan.records:
            order = record.ordine
            if order.tipo_creazione is not OrdineCreationType.AUTOMATICO:
                raise CommitPreparationError("Sono ammessi soltanto ORDINI AUTOMATICI.")
            positions = {item.order_line_position for item in record.provenance}
            if positions != set(range(1, len(order.righe) + 1)):
                raise CommitPreparationError("La provenance non copre ogni riga ORDINE.")
            if any(item.programma_fornitura_id != order.programma_fornitura_id for item in record.provenance):
                raise CommitPreparationError("La provenance appartiene a un altro PROGRAMMA.")

    def _execute(self, cursor: Any, request: CommitRequest, completed_at: CurrentSystemDate) -> CommitExecutionReceipt:
        plan = request.validated_plan.plan
        completion = request.completion
        cursor.execute(
            """SELECT id, public_id, started_at, completed_at, simulation, state, version
               FROM tpo.runs WHERE public_id = %s FOR UPDATE""",
            (completion.run_id.value,),
        )
        run = cursor.fetchone()
        if run is None:
            raise CommitExecutionError("RUN PostgreSQL assente.")
        if cursor.rowcount not in (-1, 1) or run[1] != completion.run_id.value:
            raise CommitExecutionError("Lookup RUN PostgreSQL incoerente.")
        run_id, before_state = run[0], run[5]
        if run[3] is not None or before_state is not None:
            raise CommitExecutionError("RUN PostgreSQL già conclusa.")
        if run[2] != completion.started_at.datetime or run[4] != completion.simulation:
            raise CommitExecutionError("Contesto RUN PostgreSQL incoerente.")
        if run[6] != completion.expected_version:
            raise CommitExecutionError("Versione RUN PostgreSQL in conflitto.")

        cursor.execute(
            "SELECT chiave_idempotenza FROM tpo.ordini WHERE chiave_idempotenza = ANY(%s)",
            (list(plan.idempotency_keys),),
        )
        if cursor.fetchall():
            raise CommitExistingKeyError("Una chiave idempotente del piano è già presente nel target.")

        client_ids = self._lookup(cursor, "clienti", {r.ordine.cliente_id.value for r in plan.records})
        variety_ids = self._lookup(cursor, "varieta", {line.varieta_id.value for r in plan.records for line in r.ordine.righe})
        program_ids = self._programs(cursor, plan.records, client_ids)
        program_lines = self._program_lines(cursor, plan.records, program_ids, client_ids)

        physical_lines = 0
        inserted_keys = []
        for record in plan.records:
            order = record.ordine
            cursor.execute(
                """INSERT INTO tpo.ordini
                   (public_id, cliente_id, programma_fornitura_id, run_id, data_ordine,
                    data_consegna_prevista, stato, tipo_creazione, chiave_idempotenza,
                    created_at, created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id, public_id""",
                (order.id.value, client_ids[order.cliente_id.value],
                 program_ids[order.programma_fornitura_id.value], run_id,
                 order.data_ordine, record.data_consegna_prevista, order.stato.value,
                 order.tipo_creazione.value, record.chiave_idempotenza,
                 request.requested_at.datetime, request.actor.value),
            )
            returned = cursor.fetchone()
            if cursor.rowcount != 1 or returned is None or returned[1] != order.id.value or not _positive(returned[0]):
                raise CommitExecutionError("RETURNING ORDINE incoerente.")
            order_pk = returned[0]
            line_ids = {}
            for position, line in enumerate(order.righe, 1):
                cursor.execute(
                    """INSERT INTO tpo.righe_ordine
                       (ordine_id, posizione, varieta_id, quantita, unita_misura)
                       VALUES (%s,%s,%s,%s,%s) RETURNING id, posizione""",
                    (order_pk, position, variety_ids[line.varieta_id.value], line.quantita.value, line.quantita.unit.value),
                )
                row = cursor.fetchone()
                if cursor.rowcount != 1 or row is None or not _positive(row[0]) or row[1] != position:
                    raise CommitExecutionError("RETURNING RIGA_ORDINE incoerente.")
                line_ids[position] = row[0]
                physical_lines += 1
            for origin in record.provenance:
                locator = (origin.programma_fornitura_id.value, origin.programma_version, origin.programma_line_position)
                cursor.execute(
                    "INSERT INTO tpo.origini_righe_ordine (riga_ordine_id, riga_programma_id) VALUES (%s,%s)",
                    (line_ids[origin.order_line_position], program_lines[locator]),
                )
                if cursor.rowcount != 1:
                    raise CommitExecutionError("Persistenza provenance incompleta.")
            after = {
                "public_id": order.id.value, "cliente_id": order.cliente_id.value,
                "programma_fornitura_id": order.programma_fornitura_id.value,
                "run_id": completion.run_id.value, "data_ordine": order.data_ordine.isoformat(),
                "data_consegna_prevista": record.data_consegna_prevista.isoformat(),
                "stato": order.stato.value, "tipo_creazione": order.tipo_creazione.value,
                "chiave_idempotenza": record.chiave_idempotenza,
                "righe_count": len(order.righe), "origini_count": len(record.provenance),
            }
            self._audit(cursor, completed_at, request, run_id, "ORDINE", order.id.value, "INSERT", None, after)
            inserted_keys.append(record.chiave_idempotenza)

        cursor.execute(
            """UPDATE tpo.runs SET completed_at=%s, state=%s, programmi_letti=%s,
               righe_valutate=%s, occorrenze_valutate=%s, ordini_generati=%s,
               elementi_saltati=%s, version=version+1
               WHERE id=%s AND version=%s AND completed_at IS NULL
               RETURNING public_id, version, completed_at, state""",
            (completion.completed_at.datetime, completion.final_state.value,
             completion.programmi_letti, completion.righe_valutate,
             completion.occorrenze_valutate, completion.ordini_generati,
             completion.elementi_saltati, run_id, completion.expected_version),
        )
        updated = cursor.fetchone()
        expected_update = (completion.run_id.value, completion.expected_version + 1, completion.completed_at.datetime, completion.final_state.value)
        if cursor.rowcount != 1 or updated is None or tuple(updated) != expected_update:
            raise CommitExecutionError("Completamento versionato della RUN in conflitto.")
        for kind, messages in (("WARNING", completion.warnings), ("ERROR", completion.errors)):
            for position, message in enumerate(messages, 1):
                cursor.execute("INSERT INTO tpo.run_messaggi (run_id, tipo, posizione, messaggio) VALUES (%s,%s,%s,%s)", (run_id, kind, position, message))
                if cursor.rowcount != 1:
                    raise CommitExecutionError("Persistenza messaggi RUN incompleta.")
        before = {"public_id": completion.run_id.value, "state": before_state, "version": completion.expected_version, "completed_at": None}
        after = {"public_id": completion.run_id.value, "state": completion.final_state.value,
                 "version": completion.expected_version + 1, "completed_at": completion.completed_at.datetime.isoformat(),
                 "simulation": completion.simulation, "programmi_letti": completion.programmi_letti,
                 "righe_valutate": completion.righe_valutate, "occorrenze_valutate": completion.occorrenze_valutate,
                 "ordini_generati": completion.ordini_generati, "elementi_saltati": completion.elementi_saltati}
        self._audit(cursor, completed_at, request, run_id, "RUN", completion.run_id.value, "STATE_TRANSITION", before, after)
        if physical_lines != plan.expected_logical_row_count:
            raise CommitExecutionError("Conteggio fisico RIGHE_ORDINE incoerente.")
        return CommitExecutionReceipt(plan.run_id, request.validated_plan.target_name,
            plan.expected_record_count, plan.expected_logical_row_count, physical_lines,
            tuple(inserted_keys), completed_at, True)

    @staticmethod
    def _lookup(cursor: Any, table: str, public_ids: set[str]) -> dict[str, int]:
        if table not in {"clienti", "varieta"}:
            raise ValueError("Tabella di lookup PostgreSQL non autorizzata.")
        cursor.execute(f"SELECT public_id, id FROM tpo.{table} WHERE public_id = ANY(%s)", (sorted(public_ids),))
        rows = cursor.fetchall()
        result = {row[0]: row[1] for row in rows if _positive(row[1])}
        if len(rows) != len(result) or set(result) != public_ids:
            raise CommitExecutionError(f"Lookup {table} incompleto o incoerente.")
        return result

    @staticmethod
    def _programs(
        cursor: Any, records: tuple[Any, ...], clients: dict[str, int]
    ) -> dict[str, int]:
        public_ids = {
            record.ordine.programma_fornitura_id.value for record in records
        }
        cursor.execute(
            """SELECT public_id, id, cliente_id
               FROM tpo.programmi_fornitura
               WHERE public_id = ANY(%s)""",
            (sorted(public_ids),),
        )
        rows = cursor.fetchall()
        programs = {
            public_id: (internal_id, client_id)
            for public_id, internal_id, client_id in rows
            if _positive(internal_id) and _positive(client_id)
        }
        if len(rows) != len(programs) or set(programs) != public_ids:
            raise CommitExecutionError("Lookup programmi_fornitura incompleto o incoerente.")
        if any(
            programs[record.ordine.programma_fornitura_id.value][1]
            != clients[record.ordine.cliente_id.value]
            for record in records
        ):
            raise CommitExecutionError("PROGRAMMA e CLIENTE dell'ORDINE non coincidono.")
        return {public_id: values[0] for public_id, values in programs.items()}

    @staticmethod
    def _program_lines(cursor: Any, records: tuple[Any, ...], programs: dict[str, int], clients: dict[str, int]) -> dict[tuple[str, int, int], int]:
        required = {(p.programma_fornitura_id.value, p.programma_version, p.programma_line_position) for r in records for p in r.provenance}
        result = {}
        for public_id, version, position in sorted(required):
            record = next(r for r in records if r.ordine.programma_fornitura_id.value == public_id)
            cursor.execute(
                """SELECT rp.id FROM tpo.programmi_fornitura AS p
                   JOIN tpo.programmi_fornitura_versioni AS pv ON pv.programma_fornitura_id=p.id
                   JOIN tpo.righe_programma_fornitura AS rp ON rp.programma_versione_id=pv.id
                   WHERE p.id=%s AND p.cliente_id=%s AND pv.numero_versione=%s AND rp.posizione=%s""",
                (programs[public_id], clients[record.ordine.cliente_id.value], version, position),
            )
            rows = cursor.fetchall()
            if len(rows) != 1 or not _positive(rows[0][0]):
                raise CommitExecutionError("Locator PROGRAMMA assente o incoerente.")
            result[(public_id, version, position)] = rows[0][0]
        return result

    @staticmethod
    def _audit(cursor: Any, occurred_at: CurrentSystemDate, request: CommitRequest, run_id: int,
               entity_type: str, public_id: str, operation: str, before: dict[str, Any] | None,
               after: dict[str, Any] | None) -> None:
        cursor.execute(
            """INSERT INTO tpo.audit_eventi
               (occurred_at, actor, run_id, entity_type, entity_public_id, operation,
                reason, before_data, after_data, correlation_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (occurred_at.datetime, request.actor.value, run_id, entity_type, public_id,
             operation, request.audit_reason, Jsonb(before) if before is not None else None,
             Jsonb(after) if after is not None else None, request.correlation_id),
        )
        if cursor.rowcount != 1:
            raise CommitExecutionError("Persistenza audit incompleta.")


def _positive(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


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
