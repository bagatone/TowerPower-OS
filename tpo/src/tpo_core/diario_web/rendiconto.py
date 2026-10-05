"""Compone il Rendiconto Mattutino (Fase 1, Parte A -- sola lettura/proposta,
docs/architecture/RENDICONTO_MATTUTINO_PROPOSTA.md): cosa consegnare oggi,
con lo stock/lotto gia' risolto quando possibile, e cosa seminare oggi o in
ritardo -- riusando le stesse tabelle gia' lette dai boundary
OPERATIONAL_WEB_ADAPTER esistenti (righe_piano_semina, ordini/righe_ordine/
righe_consegna, stock). Nessuna nuova tabella, nessuna scrittura qui.

Una riga di consegna finisce in "da_chiarire" quando lo stock vivo per
varieta'+unita' e' assente o insufficiente per coprirla -- mai un lotto o
una quantita' indovinati (stessa guardia gia' in vigore in ogni altro punto
di lettura/scrittura di questo sistema, OD2 della proposta).

Data di riferimento: sempre il business date Atlantic/Canary (stesso fuso
ufficiale di scheduling/production-planning), mai UTC nudo -- l'host di
Render dove gira il diario e' in UTC.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import psycopg

from ..domain.time_reference import OFFICIAL_TIMEZONE
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def _connect(settings: PostgreSQLSettings) -> psycopg.Connection:
    return psycopg.connect(
        host=settings.host, port=settings.port, dbname=settings.database,
        user=settings.user, password=settings.password, sslmode=settings.sslmode,
        connect_timeout=settings.connect_timeout_seconds,
    )


@dataclass(frozen=True)
class RigaDaSeminareOggi:
    riga_public_id: str
    varieta_denominazione: str
    cliente_denominazione: str
    stato: str
    quantita: Decimal
    unita: str
    sowing_at: datetime


@dataclass(frozen=True)
class RigaConsegnaOggi:
    ordine_public_id: str
    cliente_denominazione: str
    varieta_denominazione: str
    quantita: Decimal
    unita: str
    stock_disponibile: Decimal


@dataclass(frozen=True)
class RigaDaChiarire:
    ordine_public_id: str
    cliente_denominazione: str
    varieta_denominazione: str
    quantita_richiesta: Decimal
    unita: str
    motivo: str


@dataclass(frozen=True)
class RendicontoDelGiorno:
    data: str
    da_chiarire: tuple[RigaDaChiarire, ...]
    consegne: tuple[RigaConsegnaOggi, ...]
    da_seminare: tuple[RigaDaSeminareOggi, ...]

    @property
    def vuoto(self) -> bool:
        return not (self.da_chiarire or self.consegne or self.da_seminare)


# 2026-10-01: scoperto che possono esistere piu' tpo.piani_produzione
# contemporaneamente "correnti" (sostituita_at IS NULL sulla loro revisione
# attuale) -- es. PP-000001 (bootstrap manuale, 23/8) mai chiuso quando il
# production-planning-scheduler ha creato PP-000003 (24/9) come piano
# nuovo invece di una nuova revisione dello stesso piano. Senza scoping
# esplicito al piano piu' recente, righe_piano_semina del piano vecchio
# ricompaiono come se fossero ancora da fare (gia' verificato: il piano
# nuovo le copre tutte, nessuna persa). Root cause nello scheduler non
# ancora indagata -- qui ci si limita a leggere solo il piano vivo piu'
# recente, stesso principio del filtro sostituita_at ma esplicito.
_SELECT_DA_SEMINARE = (
    "SELECT rps.public_id, v.denominazione, c.denominazione, rps.stato, "
    "rps.quantita_residua_da_avviare, rps.unita_domanda, rps.sowing_at "
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
    "AND o.stato IN ('APERTO','PARZIALMENTE_EVASO') "
    "AND rps.sowing_at::date <= %s "
    "AND rps.quantita_residua_da_avviare > 0 "
    "ORDER BY rps.sowing_at ASC"
)

_SELECT_RESIDUO_ORDINI_OGGI = (
    "SELECT o.public_id, c.denominazione, v.denominazione, "
    "ro.quantita - COALESCE(SUM(rc.quantita) FILTER (WHERE cn.stato = 'CONSEGNATA'), 0) AS residuo, "
    "ro.unita_misura "
    "FROM tpo.righe_ordine ro "
    "JOIN tpo.ordini o ON o.id = ro.ordine_id "
    "JOIN tpo.clienti c ON c.id = o.cliente_id "
    "JOIN tpo.varieta v ON v.id = ro.varieta_id "
    "LEFT JOIN tpo.righe_consegna rc ON rc.riga_ordine_id = ro.id "
    "LEFT JOIN tpo.consegne cn ON cn.id = rc.consegna_id "
    "WHERE o.data_consegna_prevista = %s AND o.stato IN ('APERTO','PARZIALMENTE_EVASO') "
    "GROUP BY o.public_id, c.denominazione, v.denominazione, ro.quantita, ro.unita_misura "
    "HAVING ro.quantita - COALESCE(SUM(rc.quantita) FILTER (WHERE cn.stato = 'CONSEGNATA'), 0) > 0 "
    "ORDER BY c.denominazione, v.denominazione"
)

_SELECT_STOCK_VIVO = (
    "SELECT v.denominazione, s.unita_misura, s.disponibile "
    "FROM tpo.stock s JOIN tpo.varieta v ON v.id = s.varieta_id "
    "WHERE s.disponibile > 0"
)


def _risolvi_consegne(
    righe_ordine_oggi: list[tuple],
    stock_per_varieta_unita: dict[tuple[str, str], Decimal],
) -> tuple[list[RigaConsegnaOggi], list[RigaDaChiarire]]:
    consegne: list[RigaConsegnaOggi] = []
    da_chiarire: list[RigaDaChiarire] = []
    for ordine_pid, cliente_denom, varieta_denom, quantita, unita in righe_ordine_oggi:
        disponibile = stock_per_varieta_unita.get((varieta_denom, unita))
        if disponibile is None:
            da_chiarire.append(RigaDaChiarire(
                ordine_pid, cliente_denom, varieta_denom, quantita, unita,
                f"nessuno stock vivo in {unita} per {varieta_denom}",
            ))
        elif disponibile < quantita:
            da_chiarire.append(RigaDaChiarire(
                ordine_pid, cliente_denom, varieta_denom, quantita, unita,
                f"stock insufficiente: disponibili {disponibile} {unita}, richiesti {quantita} {unita}",
            ))
        else:
            consegne.append(RigaConsegnaOggi(
                ordine_pid, cliente_denom, varieta_denom, quantita, unita, disponibile,
            ))
    return consegne, da_chiarire


def componi(settings: PostgreSQLSettings, ora_riferimento: datetime) -> RendicontoDelGiorno:
    """Legge dal database reale, in questo momento, tutto cio' che serve al
    rendiconto -- nessun valore riusato da una lettura precedente."""
    oggi = ora_riferimento.astimezone(OFFICIAL_TIMEZONE).date()
    with _connect(settings) as conn, conn.cursor() as cur:
        cur.execute(_SELECT_DA_SEMINARE, (oggi,))
        da_seminare = [RigaDaSeminareOggi(*row) for row in cur.fetchall()]

        cur.execute(_SELECT_RESIDUO_ORDINI_OGGI, (oggi,))
        righe_ordine_oggi = cur.fetchall()

        cur.execute(_SELECT_STOCK_VIVO)
        stock_per_varieta_unita: dict[tuple[str, str], Decimal] = {
            (denom, unita): disp for denom, unita, disp in cur.fetchall()
        }

    consegne, da_chiarire = _risolvi_consegne(righe_ordine_oggi, stock_per_varieta_unita)
    return RendicontoDelGiorno(
        data=oggi.isoformat(),
        da_chiarire=tuple(da_chiarire),
        consegne=tuple(consegne),
        da_seminare=tuple(da_seminare),
    )
