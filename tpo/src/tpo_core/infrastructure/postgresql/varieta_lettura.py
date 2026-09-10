"""Reader PostgreSQL a sola lettura per VARIETA/LISTINO_VARIETA V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md.
Legge tpo.varieta con LEFT JOIN su tpo.listino_varieta (riga 1:1
facoltativa). Nessuna scrittura.
"""
from __future__ import annotations

import psycopg

from ...application.varieta_lettura.errors import VarietaLetturaVarietaNotFoundError
from ...application.varieta_lettura.models import (
    ElencoVarieta, RichiediElencoVarieta, RichiediVarieta, Varieta,
)
from ...domain.identifiers import VarietaId
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError

_SELECT = (
    "SELECT v.public_id, v.denominazione, v.stato, l.prezzo_unitario, l.aliquota_igic, "
    "v.created_at, v.updated_at "
    "FROM tpo.varieta v LEFT JOIN tpo.listino_varieta l ON l.varieta_id = v.id"
)


def _row_to_varieta(row) -> Varieta:
    public_id, denominazione, stato, prezzo, aliquota, created_at, updated_at = row
    return Varieta(
        VarietaId(public_id), denominazione, stato, prezzo, aliquota, created_at, updated_at,
    )


class PostgreSQLVarietaLetturaReader:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def varieta(self, query: RichiediVarieta) -> Varieta:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT} WHERE v.public_id=%s", (query.varieta_id.value,))
                row = cursor.fetchone()
                if row is None:
                    raise VarietaLetturaVarietaNotFoundError("VARIETA inesistente.")
                return _row_to_varieta(row)
        except VarietaLetturaVarietaNotFoundError:
            raise
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura VARIETA PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def elenco(self, query: RichiediElencoVarieta) -> ElencoVarieta:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT} ORDER BY v.denominazione")
                rows = cursor.fetchall()
            return ElencoVarieta(tuple(_row_to_varieta(row) for row in rows))
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura VARIETA PostgreSQL fallita.") from exc
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
