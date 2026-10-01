"""Reader PostgreSQL a sola lettura per "Da seminare" V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md
(decimo boundary). Legge tpo.righe_piano_semina (JOIN tpo.varieta,
tpo.piano_produzione_revisioni, tpo.righe_ordine, tpo.ordini, tpo.clienti),
filtrando sulla revisione CORRENTE di ogni piano
(piano_produzione_revisioni.sostituita_at IS NULL -- stesso pattern gia'
corretto per PROGRAMMA_FORNITURA nel Fatto 10 della roadmap: senza questo
filtro le righe di una revisione gia' sostituita da un replan
risulterebbero visibili come se fossero ancora da fare) e sullo stato non
ancora avviato (PIANIFICATA/PRONTA/TARDIVA). Nessuna scrittura.
"""
from __future__ import annotations

import psycopg

from ...application.pianificazione_semina_lettura.models import (
    ElencoDaSeminare,
    RichiediElencoDaSeminare,
    RigaDaSeminare,
)
from ...domain.identifiers import ClienteId, RigaPianoSeminaId, VarietaId
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError

# 2026-10-01: stesso difetto scoperto e corretto in diario_web/rendiconto.py
# (vedi commit di quella data) -- possono esistere piu' tpo.piani_produzione
# contemporaneamente "correnti" (sostituita_at IS NULL sulla loro revisione
# attuale), es. un piano vecchio mai chiuso quando il
# production-planning-scheduler ne ha creato uno nuovo invece di una nuova
# revisione dello stesso piano. Senza scoping esplicito al piano vivo piu'
# recente, righe_piano_semina del piano vecchio ricompaiono come se fossero
# ancora da fare. Aggiunto anche il filtro mancante su
# quantita_residua_da_avviare > 0 (una riga gia' coperta -- residuo zero --
# non deve comparire come "da seminare"). Nessuna nuova regola di dominio:
# resta una query pura, stesso principio del filtro sostituita_at gia' in uso,
# solo reso esplicito. Verificato con i due test esistenti (entrambi a un solo
# piano, quindi gia' compatibili) + i test di dominio/applicazione; l'ultima
# parola e' l'integrazione Postgres reale, come da D5 del freeze di questo file.
_SELECT = (
    "SELECT rps.public_id, v.public_id, v.denominazione, c.public_id, c.denominazione, "
    "rps.stato, rps.quantita_residua_da_avviare, rps.unita_domanda, "
    "rps.grammi_seme_richiesti, rps.sowing_at, rps.harvest_target_at, rps.data_consegna "
    "FROM tpo.righe_piano_semina rps "
    "JOIN tpo.varieta v ON v.id = rps.varieta_id "
    "JOIN tpo.piano_produzione_revisioni pr ON pr.id = rps.piano_revisione_id "
    "JOIN tpo.righe_ordine ro ON ro.id = rps.riga_ordine_id "
    "JOIN tpo.ordini o ON o.id = ro.ordine_id "
    "JOIN tpo.clienti c ON c.id = o.cliente_id "
    "WHERE pr.id = ( "
    "    SELECT r.id FROM tpo.piano_produzione_revisioni r "
    "    WHERE r.sostituita_at IS NULL ORDER BY r.created_at DESC LIMIT 1 "
    ") "
    "AND rps.stato IN ('PIANIFICATA','PRONTA','TARDIVA') "
    "AND rps.quantita_residua_da_avviare > 0"
)


def _row_to_riga(row) -> RigaDaSeminare:
    (
        riga_public_id, varieta_public_id, varieta_denominazione,
        cliente_public_id, cliente_denominazione, stato, quantita, unita,
        grammi, sowing_at, harvest_target_at, data_consegna,
    ) = row
    return RigaDaSeminare(
        RigaPianoSeminaId(riga_public_id),
        VarietaId(varieta_public_id),
        varieta_denominazione,
        ClienteId(cliente_public_id),
        cliente_denominazione,
        stato,
        quantita,
        unita,
        grammi,
        sowing_at,
        harvest_target_at,
        data_consegna,
    )


class PostgreSQLPianificazioneSeminaLetturaReader:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def elenco(self, query: RichiediElencoDaSeminare) -> ElencoDaSeminare:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT} ORDER BY rps.sowing_at ASC")
                rows = cursor.fetchall()
            return ElencoDaSeminare(tuple(_row_to_riga(row) for row in rows))
        except psycopg.Error as exc:
            raise PostgreSQLError('Lettura "Da seminare" PostgreSQL fallita.') from exc
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
