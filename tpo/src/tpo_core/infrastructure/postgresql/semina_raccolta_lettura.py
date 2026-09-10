"""Reader PostgreSQL a sola lettura per SEMINA/RACCOLTA V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md.
Legge tpo.semine (JOIN tpo.varieta per la denominazione) e tpo.raccolte
(JOIN su semina_id). Nessuna scrittura.
"""
from __future__ import annotations

from collections import defaultdict

import psycopg

from ...application.semina_raccolta_lettura.errors import (
    SeminaRaccoltaLetturaSeminaNotFoundError,
)
from ...application.semina_raccolta_lettura.models import (
    ElencoSemine, Raccolta, RichiediElencoSemine, RichiediSemina, Semina,
)
from ...domain.identifiers import RaccoltaId, SeminaId, VarietaId
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError

_SELECT_SEMINE = (
    "SELECT s.id, s.public_id, v.public_id, v.denominazione, s.stato, s.quantita_seme, "
    "s.unita_misura, s.data_avvio, s.causa_origine, s.esito_finale, s.cultivar_snapshot, "
    "s.lotto_seme_snapshot "
    "FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id"
)
_SELECT_RACCOLTE = (
    "SELECT r.public_id, s.public_id, r.data_raccolta, r.quantita, r.unita_misura, "
    "r.operatore, r.destinazione_prevista, r.note "
    "FROM tpo.raccolte r JOIN tpo.semine s ON s.id = r.semina_id"
)


def _row_to_raccolta(row) -> Raccolta:
    (raccolta_public_id, semina_public_id, data_raccolta, quantita, unita_misura,
     operatore, destinazione, note) = row
    return Raccolta(
        RaccoltaId(raccolta_public_id), SeminaId(semina_public_id), data_raccolta,
        quantita, unita_misura, operatore, destinazione, note,
    )


def _row_to_semina(row, raccolte: tuple[Raccolta, ...]) -> Semina:
    (_pk, public_id, varieta_public_id, varieta_denominazione, stato, quantita_seme,
     unita_misura, data_avvio, causa_origine, esito_finale, cultivar_snapshot,
     lotto_seme_snapshot) = row
    return Semina(
        SeminaId(public_id), VarietaId(varieta_public_id), varieta_denominazione, stato,
        quantita_seme, unita_misura, data_avvio, causa_origine, esito_finale,
        cultivar_snapshot, lotto_seme_snapshot, raccolte,
    )


class PostgreSQLSeminaRaccoltaLetturaReader:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def semina(self, query: RichiediSemina) -> Semina:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"{_SELECT_SEMINE} WHERE s.public_id=%s", (query.semina_id.value,)
                )
                row = cursor.fetchone()
                if row is None:
                    raise SeminaRaccoltaLetturaSeminaNotFoundError("SEMINA inesistente.")
                cursor.execute(
                    f"{_SELECT_RACCOLTE} WHERE s.public_id=%s ORDER BY r.data_raccolta",
                    (query.semina_id.value,),
                )
                raccolte = tuple(_row_to_raccolta(r) for r in cursor.fetchall())
            return _row_to_semina(row, raccolte)
        except SeminaRaccoltaLetturaSeminaNotFoundError:
            raise
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura SEMINA PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def elenco(self, query: RichiediElencoSemine) -> ElencoSemine:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_SEMINE} ORDER BY s.data_avvio DESC")
                semine_rows = cursor.fetchall()
                cursor.execute(f"{_SELECT_RACCOLTE} ORDER BY r.data_raccolta")
                raccolte_rows = cursor.fetchall()
            per_semina: dict[str, list[Raccolta]] = defaultdict(list)
            for raccolta_row in raccolte_rows:
                raccolta = _row_to_raccolta(raccolta_row)
                per_semina[raccolta.semina_id.value].append(raccolta)
            semine = tuple(
                _row_to_semina(row, tuple(per_semina.get(row[1], [])))
                for row in semine_rows
            )
            return ElencoSemine(semine)
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura SEMINA PostgreSQL fallita.") from exc
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
