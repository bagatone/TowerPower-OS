"""Reader PostgreSQL a sola lettura per SEMENTE/LOTTO_SEME V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md.
Legge tpo.sementi e tpo.lotti_seme (JOIN su semente_id). Nessuna scrittura.
"""
from __future__ import annotations

import psycopg

from ...application.semente_lettura.errors import SementeLetturaLottoNotFoundError
from ...application.semente_lettura.models import (
    ElencoLotti, ElencoSementi, LottoSeme, RichiediElencoLotti,
    RichiediElencoSementi, RichiediLotto, Semente,
)
from ...domain.identifiers import LottoSemeId
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError

_SELECT_SEMENTI = (
    "SELECT id, fornitore, referenza_commerciale, marca, trattamento, attiva FROM tpo.sementi"
)
_SELECT_LOTTI = (
    "SELECT l.public_id, s.fornitore, s.referenza_commerciale, l.numero_lotto_produttore, "
    "l.data_ricezione, l.data_scadenza, l.quantita_iniziale, l.quantita_residua, "
    "l.unita_misura, l.anomalia "
    "FROM tpo.lotti_seme l JOIN tpo.sementi s ON s.id = l.semente_id"
)


def _row_to_semente(row) -> Semente:
    semente_id, fornitore, referenza, marca, trattamento, attiva = row
    return Semente(semente_id, fornitore, referenza, marca, trattamento, attiva)


def _row_to_lotto(row) -> LottoSeme:
    (public_id, fornitore, referenza, numero_lotto, data_ricezione, data_scadenza,
     quantita_iniziale, quantita_residua, unita_misura, anomalia) = row
    return LottoSeme(
        LottoSemeId(public_id), fornitore, referenza, numero_lotto, data_ricezione,
        data_scadenza, quantita_iniziale, quantita_residua, unita_misura, anomalia,
    )


class PostgreSQLSementeLetturaReader:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def elenco_sementi(self, query: RichiediElencoSementi) -> ElencoSementi:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_SEMENTI} ORDER BY fornitore, referenza_commerciale")
                rows = cursor.fetchall()
            return ElencoSementi(tuple(_row_to_semente(row) for row in rows))
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura SEMENTI PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def lotto(self, query: RichiediLotto) -> LottoSeme:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_LOTTI} WHERE l.public_id=%s", (query.lotto_seme_id.value,))
                row = cursor.fetchone()
                if row is None:
                    raise SementeLetturaLottoNotFoundError("LOTTO_SEME inesistente.")
                return _row_to_lotto(row)
        except SementeLetturaLottoNotFoundError:
            raise
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura LOTTO_SEME PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def elenco_lotti(self, query: RichiediElencoLotti) -> ElencoLotti:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_LOTTI} ORDER BY l.data_ricezione DESC")
                rows = cursor.fetchall()
            return ElencoLotti(tuple(_row_to_lotto(row) for row in rows))
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura LOTTO_SEME PostgreSQL fallita.") from exc
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
