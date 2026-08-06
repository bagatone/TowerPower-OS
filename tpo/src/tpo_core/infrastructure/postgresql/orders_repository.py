"""Adapter PostgreSQL della porta applicativa ``OrdineRepository``."""

from __future__ import annotations

import psycopg

from ...application.scheduling.models import ScheduledOrderRecord
from ...application.scheduling.provenance import OrderLineProvenance
from ...application.write_plan.errors import InvalidWritePlanError
from ...domain.entities.ordine import Ordine, RigaOrdine
from ...domain.identifiers import ClienteId, OrdineId, ProgrammaFornituraId, VarietaId
from ...domain.quantities import Quantity, UnitOfMeasure
from ...domain.states import OrdineCreationType, OrdineState
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError


class PostgreSQLOrdineRepository:
    """Legge gli ORDINI pianificati dalle tabelle fisiche congelate."""

    def __init__(self, connection_factory: PostgreSQLConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def list_scheduled_orders(self) -> tuple[ScheduledOrderRecord, ...]:
        return self._select()

    def get_by_public_id(self, ordine_id: OrdineId) -> ScheduledOrderRecord | None:
        if not isinstance(ordine_id, OrdineId):
            raise InvalidWritePlanError("ordine_id deve essere un OrdineId.")
        records = self._select("WHERE o.public_id = %s", (ordine_id.value,))
        return records[0] if records else None

    def has_idempotency_key(self, key: str) -> bool:
        if not isinstance(key, str) or not key.strip():
            raise InvalidWritePlanError("La chiave idempotente deve essere non vuota.")
        connection = self._connection_factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM tpo.ordini WHERE chiave_idempotenza = %s)",
                    (key.strip(),),
                )
                row = cursor.fetchone()
            return bool(row[0])
        except psycopg.Error as exc:
            raise PostgreSQLError("Verifica idempotenza PostgreSQL fallita.") from exc
        finally:
            _cleanup(connection, rollback=True)

    def _select(
        self, clause: str = "", params: tuple[object, ...] = ()
    ) -> tuple[ScheduledOrderRecord, ...]:
        connection = self._connection_factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT o.public_id, c.public_id, o.data_ordine, o.stato,
                           o.tipo_creazione, p.public_id,
                           o.data_consegna_prevista, o.chiave_idempotenza,
                           r.posizione, v.public_id, r.quantita, r.unita_misura,
                           pv.numero_versione, rp.posizione
                    FROM tpo.ordini AS o
                    JOIN tpo.clienti AS c ON c.id = o.cliente_id
                    JOIN tpo.programmi_fornitura AS p ON p.id = o.programma_fornitura_id
                    JOIN tpo.righe_ordine AS r ON r.ordine_id = o.id
                    JOIN tpo.varieta AS v ON v.id = r.varieta_id
                    LEFT JOIN tpo.origini_righe_ordine AS oro ON oro.riga_ordine_id = r.id
                    LEFT JOIN tpo.righe_programma_fornitura AS rp
                      ON rp.id = oro.riga_programma_id
                    LEFT JOIN tpo.programmi_fornitura_versioni AS pv
                      ON pv.id = rp.programma_versione_id
                    {clause}
                    ORDER BY o.public_id, r.posizione, rp.posizione
                    """,
                    params,
                )
                rows = cursor.fetchall()
            return _records(rows)
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura degli ORDINI PostgreSQL fallita.") from exc
        finally:
            _cleanup(connection, rollback=True)


def _records(rows: list[tuple[object, ...]]) -> tuple[ScheduledOrderRecord, ...]:
    grouped: dict[str, list[tuple[object, ...]]] = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(row)
    result = []
    for rows_for_order in grouped.values():
        first = rows_for_order[0]
        line_rows = {}
        for row in rows_for_order:
            line_rows.setdefault(row[8], row)
        lines = tuple(
            RigaOrdine(VarietaId(row[9]), Quantity(row[10], UnitOfMeasure(row[11])))
            for row in line_rows.values()
        )
        provenance = tuple(
            OrderLineProvenance(
                programma_fornitura_id=ProgrammaFornituraId(first[5]),
                programma_version=row[12],
                programma_line_position=row[13],
                order_line_position=row[8],
            )
            for row in rows_for_order
            if len(row) > 13 and row[12] is not None and row[13] is not None
        )
        result.append(
            ScheduledOrderRecord(
                ordine=Ordine(
                    id=OrdineId(first[0]),
                    cliente_id=ClienteId(first[1]),
                    data_ordine=first[2],
                    righe=lines,
                    stato=OrdineState(first[3]),
                    tipo_creazione=OrdineCreationType(first[4]),
                    programma_fornitura_id=ProgrammaFornituraId(first[5]),
                ),
                data_consegna_prevista=first[6],
                chiave_idempotenza=first[7],
                provenance=provenance,
            )
        )
    return tuple(result)


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
