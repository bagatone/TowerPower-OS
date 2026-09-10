"""Reader PostgreSQL a sola lettura per FINANZE V1 (FATTURA/INCASSO/USCITA).

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md.
Nessuna scrittura. Vedi il docstring di
application/finanze_lettura/models.py per le scelte di scope (RIGA_FATTURA
non risolve riga_consegna_id).
"""
from __future__ import annotations

from collections import defaultdict

import psycopg

from ...application.finanze_lettura.models import (
    ElencoFatture, ElencoIncassi, ElencoUscite, Fattura, Incasso,
    RichiediElencoFatture, RichiediElencoIncassi, RichiediElencoUscite, RigaFattura, Uscita,
)
from ...domain.identifiers import ClienteId, ConsegnaId, IncassoId, NumeroFattura, UscitaId, VarietaId
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError

_SELECT_FATTURE = (
    "SELECT f.numero_fattura, cl.public_id, cl.denominazione, f.data_emissione, "
    "f.scadenza, f.totale_netto, f.totale_igic, f.totale, f.rettifica_di "
    "FROM tpo.fatture f JOIN tpo.clienti cl ON cl.id = f.cliente_id"
)
_SELECT_FATTURE_CONSEGNE = (
    "SELECT f.numero_fattura, c.public_id FROM tpo.fatture_consegne fc "
    "JOIN tpo.fatture f ON f.id = fc.fattura_id JOIN tpo.consegne c ON c.id = fc.consegna_id"
)
_SELECT_RIGHE_FATTURA = (
    "SELECT f.numero_fattura, rf.posizione, v.public_id, v.denominazione, rf.quantita, "
    "rf.unita_misura, rf.prezzo_unitario, rf.aliquota_igic, rf.importo_netto, rf.importo_igic "
    "FROM tpo.righe_fattura rf JOIN tpo.fatture f ON f.id = rf.fattura_id "
    "JOIN tpo.varieta v ON v.id = rf.varieta_id"
)
_SELECT_INCASSI = (
    "SELECT i.public_id, i.fattura_numero, i.importo, i.data_incasso, i.metodo, i.note, "
    "r.public_id, i.created_at "
    "FROM tpo.incassi i LEFT JOIN tpo.incassi r ON r.id = i.rettifica_incasso_id"
)
_SELECT_USCITE = (
    "SELECT u.public_id, u.importo, u.data_uscita, u.categoria, u.beneficiario, u.metodo, "
    "u.note, r.public_id, u.created_at "
    "FROM tpo.uscite u LEFT JOIN tpo.uscite r ON r.id = u.rettifica_uscita_id"
)


class PostgreSQLFinanzeLetturaReader:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def fatture(self, query: RichiediElencoFatture) -> ElencoFatture:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_FATTURE} ORDER BY f.data_emissione DESC")
                fatture_rows = cursor.fetchall()
                cursor.execute(f"{_SELECT_FATTURE_CONSEGNE} ORDER BY fc.posizione")
                consegne_rows = cursor.fetchall()
                cursor.execute(f"{_SELECT_RIGHE_FATTURA} ORDER BY rf.posizione")
                righe_rows = cursor.fetchall()
            consegne_per_fattura: dict[str, list[ConsegnaId]] = defaultdict(list)
            for numero_fattura, consegna_public_id in consegne_rows:
                consegne_per_fattura[numero_fattura].append(ConsegnaId(consegna_public_id))
            righe_per_fattura: dict[str, list[RigaFattura]] = defaultdict(list)
            for row in righe_rows:
                (numero_fattura, posizione, varieta_public_id, varieta_denominazione, quantita,
                 unita_misura, prezzo_unitario, aliquota_igic, importo_netto,
                 importo_igic) = row
                righe_per_fattura[numero_fattura].append(RigaFattura(
                    posizione, VarietaId(varieta_public_id), varieta_denominazione, quantita,
                    unita_misura, prezzo_unitario, aliquota_igic, importo_netto, importo_igic,
                ))
            fatture = tuple(
                Fattura(
                    NumeroFattura(numero_fattura), ClienteId(cl_public_id), cl_denominazione,
                    data_emissione, scadenza, totale_netto, totale_igic, totale,
                    NumeroFattura(rettifica_di) if rettifica_di is not None else None,
                    tuple(consegne_per_fattura.get(numero_fattura, [])),
                    tuple(righe_per_fattura.get(numero_fattura, [])),
                )
                for (numero_fattura, cl_public_id, cl_denominazione, data_emissione, scadenza,
                     totale_netto, totale_igic, totale, rettifica_di) in fatture_rows
            )
            return ElencoFatture(fatture)
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura FATTURE PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def incassi(self, query: RichiediElencoIncassi) -> ElencoIncassi:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_INCASSI} ORDER BY i.data_incasso DESC")
                rows = cursor.fetchall()
            incassi = tuple(
                Incasso(
                    IncassoId(public_id), NumeroFattura(fattura_numero), importo, data_incasso,
                    metodo, note,
                    IncassoId(rettifica_public_id) if rettifica_public_id is not None else None,
                    created_at,
                )
                for (public_id, fattura_numero, importo, data_incasso, metodo, note,
                     rettifica_public_id, created_at) in rows
            )
            return ElencoIncassi(incassi)
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura INCASSI PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def uscite(self, query: RichiediElencoUscite) -> ElencoUscite:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_USCITE} ORDER BY u.data_uscita DESC")
                rows = cursor.fetchall()
            uscite = tuple(
                Uscita(
                    UscitaId(public_id), importo, data_uscita, categoria, beneficiario, metodo,
                    note, UscitaId(rettifica_public_id) if rettifica_public_id is not None else None,
                    created_at,
                )
                for (public_id, importo, data_uscita, categoria, beneficiario, metodo, note,
                     rettifica_public_id, created_at) in rows
            )
            return ElencoUscite(uscite)
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura USCITE PostgreSQL fallita.") from exc
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
