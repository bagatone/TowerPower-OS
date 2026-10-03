"""Reader PostgreSQL a sola lettura per la BOLLA DI CONSEGNA.

Legge tpo.consegne (JOIN tpo.clienti), tpo.righe_consegna (JOIN tpo.varieta,
tpo.ordini) e, per la provenienza di lotto, la catena
righe_consegna -> movimenti_magazzino (SCARICO) -> consumi_lotto ->
movimenti_magazzino (CARICO) -> raccolte -> semine.codice_tracciabilita.
Nessuna scrittura. Un lotto senza codice di tracciabilita' risolvibile non
viene mai mostrato: la sua quantita' resta "senza origine".
"""
from __future__ import annotations

from decimal import Decimal

import psycopg

from ...application.bolla_lettura.errors import ConsegnaNonTrovataError
from ...application.bolla_lettura.models import (
    Bolla, OrigineLotto, RichiediBolla, RigaBolla,
)
from ...domain.identifiers import ConsegnaId
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError

_SELECT_CONSEGNA = (
    "SELECT c.id, c.stato, c.data_prevista, c.data_effettiva, c.operatore, "
    "c.destinazione_fisica, cl.public_id, cl.denominazione "
    "FROM tpo.consegne c JOIN tpo.clienti cl ON cl.id = c.cliente_id "
    "WHERE c.public_id = %s"
)
_SELECT_RIGHE = (
    "SELECT rc.id, rc.posizione, o.public_id, v.public_id, v.denominazione, "
    "rc.quantita, rc.unita_misura, (rc.rettifica_riga_consegna_id IS NOT NULL) "
    "FROM tpo.righe_consegna rc "
    "JOIN tpo.varieta v ON v.id = rc.varieta_id "
    "JOIN tpo.ordini o ON o.id = rc.ordine_id "
    "WHERE rc.consegna_id = %s ORDER BY rc.posizione"
)
_SELECT_ORIGINI = (
    "SELECT rc.id, s.codice_tracciabilita, r.public_id, r.data_raccolta, cl.quantita "
    "FROM tpo.righe_consegna rc "
    "JOIN tpo.movimenti_magazzino ms "
    "  ON ms.riga_consegna_id = rc.id AND ms.tipo = 'SCARICO' "
    "JOIN tpo.consumi_lotto cl "
    "  ON cl.movimento_scarico_id = ms.id AND cl.tipo_consumo = 'CONSEGNA' "
    "JOIN tpo.movimenti_magazzino mc ON mc.id = cl.movimento_carico_id "
    "JOIN tpo.raccolte r ON r.id = mc.raccolta_id "
    "JOIN tpo.semine s ON s.id = r.semina_id "
    "WHERE rc.consegna_id = %s AND s.codice_tracciabilita IS NOT NULL "
    "ORDER BY rc.id, mc.data_movimento, mc.id"
)


class PostgreSQLBollaLetturaReader:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def bolla(self, query: RichiediBolla) -> Bolla:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(_SELECT_CONSEGNA, (query.consegna_id.value,))
                head = cursor.fetchone()
                if head is None:
                    raise ConsegnaNonTrovataError(
                        f"CONSEGNA {query.consegna_id.value} non trovata."
                    )
                (consegna_pk, stato, data_prevista, data_effettiva, operatore,
                 destinazione, cliente_public_id, cliente_denominazione) = head
                cursor.execute(_SELECT_RIGHE, (consegna_pk,))
                righe_rows = cursor.fetchall()
                cursor.execute(_SELECT_ORIGINI, (consegna_pk,))
                origini_rows = cursor.fetchall()
            origini_per_riga: dict[int, list[OrigineLotto]] = {}
            for riga_pk, codice, raccolta_id, data_raccolta, quantita in origini_rows:
                origini_per_riga.setdefault(riga_pk, []).append(
                    OrigineLotto(codice, raccolta_id, data_raccolta, Decimal(quantita))
                )
            righe = []
            for (riga_pk, posizione, ordine_id, varieta_id, varieta_nome,
                 quantita, unita, rettifica) in righe_rows:
                quantita = Decimal(quantita)
                origini = tuple(origini_per_riga.get(riga_pk, ()))
                spiegata = sum((o.quantita for o in origini), Decimal(0))
                senza_origine = max(quantita - spiegata, Decimal(0)) if quantita > 0 else Decimal(0)
                righe.append(RigaBolla(
                    posizione, ordine_id, varieta_id, varieta_nome, quantita, unita,
                    bool(rettifica), origini, senza_origine,
                ))
            return Bolla(
                ConsegnaId(query.consegna_id.value), stato, cliente_public_id,
                cliente_denominazione, data_prevista, data_effettiva, operatore,
                destinazione, tuple(righe),
            )
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura BOLLA PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    @staticmethod
    def _release(connection) -> None:
        try:
            connection.rollback()
        except Exception:
            pass
