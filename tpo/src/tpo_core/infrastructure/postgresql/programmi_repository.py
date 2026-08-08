"""Repository PostgreSQL read-only dei PROGRAMMI versionati."""

from __future__ import annotations

import psycopg

from ...application.scheduling.provenance import (
    VersionedProgramLine,
    VersionedProgrammaFornitura,
)
from ...domain.entities.programma_fornitura import (
    ConfigurazioneTemporale,
    ProgrammaFornitura,
    RigaProgrammaFornitura,
    TipoRicorrenza,
)
from ...domain.identifiers import ClienteId, ProgrammaFornituraId, VarietaId
from ...domain.quantities import Quantity, UnitOfMeasure
from ...domain.states import ProgrammaFornituraState
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError


class PostgreSQLVersionedProgrammaFornituraRepository:
    """Legge le versioni correnti e le posizioni autorevoli delle righe."""

    def __init__(self, connection_factory: PostgreSQLConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def list_versioned_for_scheduling(
        self,
    ) -> tuple[VersionedProgrammaFornitura, ...]:
        connection = self._connection_factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT p.public_id, c.public_id, pv.numero_versione, pv.stato,
                           pv.data_inizio, pv.data_fine, pv.orario_generazione,
                           pv.finestra_operativa_giorni, rp.posizione, v.public_id,
                           rp.quantita, rp.unita_misura, rp.tipo_ricorrenza,
                           rp.intervallo_giorni,
                           ARRAY(
                               SELECT rpg.giorno_iso
                               FROM tpo.righe_programma_giorni AS rpg
                               WHERE rpg.riga_programma_id = rp.id
                               ORDER BY rpg.giorno_iso
                           )
                    FROM tpo.programmi_fornitura AS p
                    JOIN tpo.clienti AS c ON c.id = p.cliente_id
                    JOIN tpo.programmi_fornitura_versioni AS pv
                      ON pv.programma_fornitura_id = p.id
                     AND pv.cliente_id = p.cliente_id
                    JOIN tpo.righe_programma_fornitura AS rp
                      ON rp.programma_versione_id = pv.id
                    JOIN tpo.varieta AS v ON v.id = rp.varieta_id
                    WHERE pv.valida_al IS NULL
                    ORDER BY p.public_id, rp.posizione
                    """,
                    (),
                )
                rows = cursor.fetchall()
            return _programmi(rows)
        except psycopg.Error as exc:
            raise PostgreSQLError(
                "Lettura dei PROGRAMMI PostgreSQL fallita."
            ) from exc
        finally:
            _cleanup(connection)


def _programmi(
    rows: list[tuple[object, ...]],
) -> tuple[VersionedProgrammaFornitura, ...]:
    grouped: dict[str, list[tuple[object, ...]]] = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(row)
    result = []
    for program_rows in grouped.values():
        first = program_rows[0]
        locators = tuple(
            VersionedProgramLine(
                position=row[8],
                line=RigaProgrammaFornitura(
                    varieta_id=VarietaId(row[9]),
                    quantita=Quantity(row[10], UnitOfMeasure(row[11])),
                    configurazione_temporale=ConfigurazioneTemporale(
                        tipo=TipoRicorrenza(row[12]),
                        intervallo_giorni=row[13],
                        giorni_settimana=tuple(row[14]),
                    ),
                ),
            )
            for row in program_rows
        )
        programma = ProgrammaFornitura(
            id=ProgrammaFornituraId(first[0]),
            cliente_id=ClienteId(first[1]),
            righe=tuple(locator.line for locator in locators),
            data_inizio=first[4],
            data_fine=first[5],
            orario_generazione=first[6],
            stato=ProgrammaFornituraState(first[3]),
            finestra_operativa_giorni=first[7],
        )
        result.append(
            VersionedProgrammaFornitura(
                programma=programma,
                version=first[2],
                lines=locators,
            )
        )
    return tuple(result)


def _cleanup(connection: object) -> None:
    try:
        connection.rollback()
    except Exception:
        pass
    try:
        connection.close()
    except Exception:
        pass
