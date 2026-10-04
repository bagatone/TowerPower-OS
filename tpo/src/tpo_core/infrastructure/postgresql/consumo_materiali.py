"""Reader PostgreSQL a sola lettura per CONSUMO_MATERIALI_SEMINA V1."""
from __future__ import annotations

import psycopg

from ...application.consumo_materiali.models import SeminaPerConsumo
from ...domain.identifiers import ArticoloId, SeminaId
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError


class PostgreSQLConsumoMaterialiReader:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def _fetch(self, sql: str, params: tuple):
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura CONSUMO_MATERIALI non riuscita.") from exc
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()

    def trova_semina(self, semina_id: SeminaId) -> SeminaPerConsumo | None:
        rows = self._fetch(
            """SELECT s.public_id, s.codice_tracciabilita, v.denominazione, s.data_avvio
               FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id
               WHERE s.public_id = %s""",
            (semina_id.value,),
        )
        if not rows:
            return None
        pid, codice, varieta, data_avvio = rows[0]
        return SeminaPerConsumo(SeminaId(pid), codice, varieta, data_avvio)

    def trova_articoli_per_denominazione(self, denominazione: str) -> list[ArticoloId]:
        rows = self._fetch(
            "SELECT public_id FROM tpo.articoli WHERE lower(denominazione) = lower(%s) "
            "ORDER BY public_id",
            (denominazione,),
        )
        return [ArticoloId(r[0]) for r in rows]

    def articolo_esiste(self, articolo_id: ArticoloId) -> bool:
        return bool(self._fetch(
            "SELECT 1 FROM tpo.articoli WHERE public_id = %s", (articolo_id.value,),
        ))
