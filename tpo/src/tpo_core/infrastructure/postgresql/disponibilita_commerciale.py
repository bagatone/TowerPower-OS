"""Reader PostgreSQL a sola lettura per DISPONIBILITA_COMMERCIALE V1.

Autorità: docs/architecture/STOCK_DISPONIBILITA_COMMERCIALE_FREEZE.md. Non
scrive mai su tpo.stock: PRENOTATO è calcolato on-demand dalle RIGHE_ORDINE
non ancora completamente evase (ORDINE in APERTO o PARZIALMENTE_EVASO), meno
quanto già consegnato (tpo.righe_consegna collegate a una tpo.consegne con
stato='CONSEGNATA' -- stessa definizione di "delivered" usata da
fn_check_fulfilment_bounds/fn_check_ordine_fulfilment_state; una riga_consegna
il cui segno include già le eventuali rettifiche -- ck_righe_consegna_ordinary_or_correction --
non conta finché la sua CONSEGNA non è effettivamente CONSEGNATA). VENDIBILE
= DISPONIBILE (tpo.stock, invariato) - PRENOTATO; se negativo, il chiamante
riceve integrita_allarme=True (nessuna scrittura, solo segnalazione, per
Owner Decision D-STOCK-read-model).
"""
from __future__ import annotations

from decimal import Decimal

import psycopg

from ...application.disponibilita_commerciale.errors import (
    DisponibilitaCommercialeStockConflictError,
    DisponibilitaCommercialeVarietaNotFoundError,
)
from ...application.disponibilita_commerciale.models import (
    DisponibilitaCommerciale, RichiediDisponibilitaCommerciale,
)
from ...domain.identifiers import VarietaId
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError

_DEFAULT_UOM = "GRAM"


class PostgreSQLDisponibilitaCommercialeReader:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    @staticmethod
    def _resolve_stock_row(stock_rows: list) -> tuple:
        """Applica la politica confermata (Owner Decision 19/9/2026): con
        tpo.stock a chiave composita una VARIETA puo' avere piu' righe, una
        per unita'. Nessuna riga -> 0/_DEFAULT_UOM (invariato). Una sola
        riga -> quella, invariato anche se disponibile=0 (es. STOCK storico
        mai piu' toccato). Piu' righe -> si preferisce l'unica con
        disponibile>0; se questo e' ambiguo (zero righe vive o piu' di una)
        si fallisce chiuso invece di indovinare."""
        if not stock_rows:
            return Decimal(0), _DEFAULT_UOM
        if len(stock_rows) == 1:
            return Decimal(stock_rows[0][0]), stock_rows[0][1]
        live = [row for row in stock_rows if Decimal(row[0]) > 0]
        if len(live) != 1:
            raise DisponibilitaCommercialeStockConflictError(
                "Piu' righe STOCK per questa VARIETA senza un'unica riga viva "
                "(disponibile>0): impossibile determinare la disponibilita' "
                "commerciale senza ambiguita'."
            )
        return Decimal(live[0][0]), live[0][1]

    def disponibilita(
        self, query: RichiediDisponibilitaCommerciale
    ) -> DisponibilitaCommerciale:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM tpo.varieta WHERE public_id=%s",
                    (query.varieta_id.value,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise DisponibilitaCommercialeVarietaNotFoundError(
                        "VARIETA inesistente."
                    )
                varieta_pk = row[0]

                cursor.execute(
                    "SELECT disponibile,unita_misura FROM tpo.stock WHERE varieta_id=%s",
                    (varieta_pk,),
                )
                stock_rows = cursor.fetchall()
                disponibile, unita_misura = self._resolve_stock_row(stock_rows)

                cursor.execute(
                    """SELECT COALESCE(SUM(GREATEST(ro.quantita - COALESCE(rc.consegnato, 0), 0)), 0)
                       FROM tpo.righe_ordine ro
                       JOIN tpo.ordini o ON o.id = ro.ordine_id
                       LEFT JOIN (
                           SELECT rc.riga_ordine_id, SUM(rc.quantita) AS consegnato
                           FROM tpo.righe_consegna rc
                           JOIN tpo.consegne c ON c.id = rc.consegna_id
                           WHERE c.stato = 'CONSEGNATA'
                           GROUP BY rc.riga_ordine_id
                       ) rc ON rc.riga_ordine_id = ro.id
                       WHERE ro.varieta_id = %s AND o.stato IN ('APERTO','PARZIALMENTE_EVASO')""",
                    (varieta_pk,),
                )
                prenotato = Decimal(cursor.fetchone()[0])
            vendibile = disponibile - prenotato
            return DisponibilitaCommerciale(
                query.varieta_id, unita_misura, disponibile, prenotato, vendibile,
                vendibile < 0,
            )
        except (
            DisponibilitaCommercialeVarietaNotFoundError,
            DisponibilitaCommercialeStockConflictError,
        ):
            raise
        except psycopg.Error as exc:
            raise PostgreSQLError(
                "Lettura DISPONIBILITA_COMMERCIALE PostgreSQL fallita."
            ) from exc
        finally:
            try:
                connection.rollback()
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass
