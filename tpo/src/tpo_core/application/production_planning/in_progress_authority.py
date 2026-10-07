"""Regole pure della produzione in corso (SEMINA) per Production Planning.

Addendum 6/10/2026 (Owner: Matteo). Tre regole, condivise da loader, commit writer, assembler e dal comando
governato di commissioning predittivo, cosi' nessuno le ricalcola in modo diverso (lezione di HARVEST_CHANGED):

1. ``derive_in_progress_authority``: quantita' utile attesa e finestra di raccolta di una SEMINA fisica, derivate
   SOLO dalla versione di protocollo con cui e' stata seminata (nessun dato inventato):
     quantita'  = SET DICHIARATI dal titolare (intero) x resa attesa del protocollo (solo se la resa e'
                  espressa in SET; altrimenti nessuna derivazione). Un SET resta sempre un SET: i grammi di
                  seme NON definiscono il numero di SET (regola di Matteo, 6/10/2026: es. un SET sperimentale
                  con 7 g invece di 8 g e' comunque 1 SET); servono solo alla tracciabilita' del seme.
     inizio     = avvio fisico + giorni di germinazione + giorni di luce/crescita + buffer temporale (minuti)
     fine       = inizio + ``window_days`` giorni (default 5, scelta di Matteo)
2. ``in_progress_eligible_quantity``: la resa gia' RACCOLTA (registrata in raccolte) non e' piu' produzione
   in corso (e' RACCOLTA/STOCK): eleggibile = max(allocata, attesa - raccolta), mai negativa.
3. ``in_progress_compatible_with_delivery``: la semina e' eleggibile per una consegna solo se la sua finestra
   inizia entro (consegna - anticipo minimo di raccolta). E' un FILTRO di eleggibilita' (contratto congelato),
   non una condizione di errore del run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_DOWN

from ...domain.time_reference import OFFICIAL_TIMEZONE

DEFAULT_WINDOW_DAYS = 5
_SIX = Decimal("0.000001")


@dataclass(frozen=True)
class InProgressAuthority:
    quantity: Decimal
    uom: str
    window_start: datetime
    window_end: datetime


def derive_in_progress_authority(
    *,
    declared_sets: int,
    expected_yield: Decimal,
    yield_uom: str,
    started_at: datetime,
    germination_days: int,
    light_days: int,
    buffer_minutes: int,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> InProgressAuthority | None:
    if yield_uom != "SET" or started_at.tzinfo is None or window_days < 1:
        return None
    if isinstance(declared_sets, bool) or not isinstance(declared_sets, int) or declared_sets < 1:
        return None
    if expected_yield <= 0:
        return None
    quantity = (Decimal(declared_sets) * Decimal(expected_yield)).quantize(_SIX, rounding=ROUND_DOWN)
    if quantity <= 0:
        return None
    start = started_at + timedelta(days=int(germination_days) + int(light_days), minutes=int(buffer_minutes or 0))
    return InProgressAuthority(quantity, "SET", start, start + timedelta(days=window_days))


def in_progress_eligible_quantity(expected: Decimal, harvested: Decimal, allocated: Decimal) -> Decimal:
    return max(Decimal(allocated), Decimal(expected) - Decimal(harvested), Decimal("0"))


def in_progress_compatible_with_delivery(
    window_start: datetime, delivery_date: date, harvest_min_lead_days: int
) -> bool:
    return window_start.astimezone(OFFICIAL_TIMEZONE).date() <= delivery_date - timedelta(days=harvest_min_lead_days)
