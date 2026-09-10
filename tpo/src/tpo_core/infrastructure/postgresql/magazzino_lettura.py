"""Reader PostgreSQL a sola lettura per MAGAZZINO V1 (STOCK/MOVIMENTO/ARTICOLO).

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md.
Legge tpo.articoli, tpo.stock (JOIN tpo.varieta), tpo.stock_articoli (JOIN
tpo.articoli), tpo.movimenti_magazzino (LEFT JOIN tpo.varieta/tpo.articoli/
tpo.raccolte/tpo.consegne/tpo.runs). Nessuna scrittura.
"""
from __future__ import annotations

import psycopg

from ...application.magazzino_lettura.models import (
    Articolo, ElencoArticoli, ElencoMovimenti, ElencoStock, MovimentoMagazzino,
    RichiediElencoArticoli, RichiediElencoMovimenti, RichiediElencoStock,
    StockArticolo, StockVarieta,
)
from ...domain.identifiers import (
    ArticoloId, ConsegnaId, MovimentoId, RaccoltaId, RunId, VarietaId,
)
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError

_SELECT_ARTICOLI = (
    "SELECT public_id, denominazione, unita_misura, created_at FROM tpo.articoli"
)
_SELECT_STOCK_VARIETA = (
    "SELECT v.public_id, v.denominazione, s.disponibile, s.unita_misura, "
    "s.updated_at, s.version FROM tpo.stock s JOIN tpo.varieta v ON v.id = s.varieta_id"
)
_SELECT_STOCK_ARTICOLI = (
    "SELECT a.public_id, a.denominazione, sa.disponibile, sa.unita_misura, "
    "sa.updated_at, sa.version FROM tpo.stock_articoli sa "
    "JOIN tpo.articoli a ON a.id = sa.articolo_id"
)
_SELECT_MOVIMENTI = (
    "SELECT m.public_id, v.public_id, v.denominazione, a.public_id, a.denominazione, "
    "m.unita_misura, m.tipo, m.direzione, m.quantita, m.data_movimento, m.motivo, "
    "m.origine_tipo, m.origine_riferimento, r.public_id, c.public_id, run.public_id, "
    "m.created_at "
    "FROM tpo.movimenti_magazzino m "
    "LEFT JOIN tpo.varieta v ON v.id = m.varieta_id "
    "LEFT JOIN tpo.articoli a ON a.id = m.articolo_id "
    "LEFT JOIN tpo.raccolte r ON r.id = m.raccolta_id "
    "LEFT JOIN tpo.consegne c ON c.id = m.consegna_id "
    "LEFT JOIN tpo.runs run ON run.id = m.run_id"
)


def _row_to_articolo(row) -> Articolo:
    public_id, denominazione, unita_misura, created_at = row
    return Articolo(ArticoloId(public_id), denominazione, unita_misura, created_at)


def _row_to_stock_varieta(row) -> StockVarieta:
    varieta_public_id, denominazione, disponibile, unita_misura, updated_at, version = row
    return StockVarieta(
        VarietaId(varieta_public_id), denominazione, disponibile, unita_misura,
        updated_at, version,
    )


def _row_to_stock_articolo(row) -> StockArticolo:
    articolo_public_id, denominazione, disponibile, unita_misura, updated_at, version = row
    return StockArticolo(
        ArticoloId(articolo_public_id), denominazione, disponibile, unita_misura,
        updated_at, version,
    )


def _row_to_movimento(row) -> MovimentoMagazzino:
    (public_id, varieta_public_id, varieta_denominazione, articolo_public_id,
     articolo_denominazione, unita_misura, tipo, direzione, quantita, data_movimento,
     motivo, origine_tipo, origine_riferimento, raccolta_public_id, consegna_public_id,
     run_public_id, created_at) = row
    return MovimentoMagazzino(
        MovimentoId(public_id),
        VarietaId(varieta_public_id) if varieta_public_id is not None else None,
        varieta_denominazione,
        ArticoloId(articolo_public_id) if articolo_public_id is not None else None,
        articolo_denominazione,
        unita_misura, tipo, direzione, quantita, data_movimento, motivo,
        origine_tipo, origine_riferimento,
        RaccoltaId(raccolta_public_id) if raccolta_public_id is not None else None,
        ConsegnaId(consegna_public_id) if consegna_public_id is not None else None,
        RunId(run_public_id) if run_public_id is not None else None,
        created_at,
    )


class PostgreSQLMagazzinoLetturaReader:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def articoli(self, query: RichiediElencoArticoli) -> ElencoArticoli:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_ARTICOLI} ORDER BY denominazione")
                rows = cursor.fetchall()
            return ElencoArticoli(tuple(_row_to_articolo(r) for r in rows))
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura ARTICOLI PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def stock(self, query: RichiediElencoStock) -> ElencoStock:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_STOCK_VARIETA} ORDER BY v.denominazione")
                varieta_rows = cursor.fetchall()
                cursor.execute(f"{_SELECT_STOCK_ARTICOLI} ORDER BY a.denominazione")
                articoli_rows = cursor.fetchall()
            return ElencoStock(
                tuple(_row_to_stock_varieta(r) for r in varieta_rows),
                tuple(_row_to_stock_articolo(r) for r in articoli_rows),
            )
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura STOCK PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def movimenti(self, query: RichiediElencoMovimenti) -> ElencoMovimenti:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_MOVIMENTI} ORDER BY m.data_movimento DESC")
                rows = cursor.fetchall()
            return ElencoMovimenti(tuple(_row_to_movimento(r) for r in rows))
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura MOVIMENTI_MAGAZZINO PostgreSQL fallita.") from exc
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
