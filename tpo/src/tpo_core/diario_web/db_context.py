"""Query di sola lettura per dare al modello (e all'utente) il contesto
reale su cui basare una proposta -- mai inventare un varieta_id, un
lotto seme o un protocollo: si leggono sempre qui, appena prima di
costruire la proposta, e poi si rileggono di nuovo (vedi actions.py)
un istante prima di eseguire davvero, cosi' un dato "invecchiato" di
pochi secondi non puo' mai finire in una scrittura reale.

Nessuna scrittura in questo file (guardia D del freeze
OPERATIONAL_WEB_ADAPTER: l'adapter web non e' mai un secondo Writer --
qui vale anche per le sole letture di supporto al diario).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import psycopg

from ..infrastructure.postgresql.settings import PostgreSQLSettings


def _connect(settings: PostgreSQLSettings) -> psycopg.Connection:
    return psycopg.connect(
        host=settings.host, port=settings.port, dbname=settings.database,
        user=settings.user, password=settings.password, sslmode=settings.sslmode,
        connect_timeout=settings.connect_timeout_seconds,
    )


@dataclass(frozen=True)
class VarietaInfo:
    public_id: str
    denominazione: str
    codice: str


@dataclass(frozen=True)
class SeminaAttiva:
    public_id: str
    stato: str
    version: int
    codice_tracciabilita: str
    data_avvio: str


@dataclass(frozen=True)
class LottoProtocolloCandidato:
    lotto_seme_public_id: str
    lotto_seme_version: int
    fornitore: str
    referenza_commerciale: str
    quantita_residua: Decimal
    protocollo_versione_public_id: str
    grammi_seme_per_set: Decimal
    anomalia: str | None


def elenca_varieta(settings: PostgreSQLSettings) -> list[VarietaInfo]:
    with _connect(settings) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT public_id, denominazione, codice_tracciabilita FROM tpo.varieta "
            "WHERE stato = 'ATTIVA' ORDER BY denominazione"
        )
        return [VarietaInfo(*row) for row in cur.fetchall()]


def semine_attive_per_varieta(settings: PostgreSQLSettings, varieta_public_id: str) -> list[SeminaAttiva]:
    with _connect(settings) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT s.public_id, s.stato, s.version, s.codice_tracciabilita, s.data_avvio::text
               FROM tpo.semine s
               JOIN tpo.varieta v ON v.id = s.varieta_id
               WHERE v.public_id = %s AND s.stato <> 'CHIUSA'
               ORDER BY s.data_avvio""",
            (varieta_public_id,),
        )
        return [SeminaAttiva(*row) for row in cur.fetchall()]


def candidati_lotto_protocollo(
    settings: PostgreSQLSettings, varieta_public_id: str
) -> list[LottoProtocolloCandidato]:
    """Lotti seme collegati (via semente_impieghi) a un protocollo APPROVATA
    corrente per questa varieta, con seme ancora disponibile. Puo' restituire
    piu' di un candidato -- in quel caso chi chiama non deve scegliere da
    solo, deve fermarsi e chiedere (stessa regola gia' applicata a mano piu'
    volte in questa sessione)."""
    with _connect(settings) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT ls.public_id, ls.version, s.fornitore, s.referenza_commerciale,
                      ls.quantita_residua, pv.public_id, pv.grammi_seme_per_set, ls.anomalia
               FROM tpo.semente_impieghi si
               JOIN tpo.sementi s ON s.id = si.semente_id
               JOIN tpo.lotti_seme ls ON ls.semente_id = s.id
               JOIN tpo.cultivar_usi cu ON cu.id = si.cultivar_uso_id
               JOIN tpo.cultivar c ON c.id = cu.cultivar_id
               JOIN tpo.varieta v ON v.id = c.varieta_id
               JOIN tpo.protocolli p ON p.cultivar_uso_id = cu.id
               JOIN tpo.protocollo_versioni pv ON pv.protocollo_id = p.id
               WHERE v.public_id = %s
                 AND pv.stato_approvazione = 'APPROVATA' AND pv.valida_al IS NULL
                 AND ls.quantita_residua > 0
               ORDER BY ls.public_id""",
            (varieta_public_id,),
        )
        return [LottoProtocolloCandidato(*row) for row in cur.fetchall()]
