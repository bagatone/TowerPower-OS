"""Reader PostgreSQL a sola lettura per CLIENTI V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md.
Legge esclusivamente tpo.clienti, nessuna scrittura.
"""
from __future__ import annotations

import psycopg

from ...application.clienti_lettura.errors import ClientiLetturaClienteNotFoundError
from ...application.clienti_lettura.models import (
    Cliente, ElencoClienti, RichiediCliente, RichiediElencoClienti,
)
from ...domain.identifiers import ClienteId
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError

_SELECT = (
    "SELECT public_id, denominazione, modalita_fatturazione, "
    "termini_pagamento_giorni, created_at, updated_at FROM tpo.clienti"
)


def _row_to_cliente(row) -> Cliente:
    public_id, denominazione, modalita, termini, created_at, updated_at = row
    return Cliente(
        ClienteId(public_id), denominazione, modalita, termini, created_at, updated_at,
    )


class PostgreSQLClientiLetturaReader:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def cliente(self, query: RichiediCliente) -> Cliente:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT} WHERE public_id=%s", (query.cliente_id.value,))
                row = cursor.fetchone()
                if row is None:
                    raise ClientiLetturaClienteNotFoundError("CLIENTE inesistente.")
                return _row_to_cliente(row)
        except ClientiLetturaClienteNotFoundError:
            raise
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura CLIENTI PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def elenco(self, query: RichiediElencoClienti) -> ElencoClienti:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT} ORDER BY denominazione")
                rows = cursor.fetchall()
            return ElencoClienti(tuple(_row_to_cliente(row) for row in rows))
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura CLIENTI PostgreSQL fallita.") from exc
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
