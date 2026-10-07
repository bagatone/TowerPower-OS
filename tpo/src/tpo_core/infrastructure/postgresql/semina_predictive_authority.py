"""Commissioning governato dell'autorita' predittiva delle SEMINE in corso.

Addendum 6/10/2026 (Owner: Matteo). Il freeze SEMINA_COMMISSIONING_BOUNDARY §10 impone che ``semina commission``
lasci NULLI quantita' utile attesa e finestra di raccolta e rinvia a "una separata autorita' governata di
predictive-resource commissioning" che li popoli TUTTI E QUATTRO atomicamente. Questo modulo ne e' la prima
implementazione (da ratificare con il freeze di architettura): senza, il planner non vede la produzione fisica.

Regole (``application.production_planning.in_progress_authority``):
- il NUMERO DI SET e' un intero DICHIARATO dal titolare (un SET resta un SET: un SET sperimentale con meno seme
  e' comunque 1 SET); i grammi di seme non lo definiscono. Il modulo PROPONE un intero solo quando i grammi
  corrispondono esattamente a un numero intero di SET del protocollo; altrimenti il numero va dichiarato.
- quantita' utile = SET dichiarati x resa del protocollo (solo se in SET); finestra = avvio + germinazione +
  luce/crescita + buffer, di durata ``window_days`` (default 5).
- una semina con i quattro campi gia' popolati NON si tocca (correzione = decisione separata, non supportata qui):
  se coincidono con la derivazione e' un replay compatibile, se differiscono si rifiuta.
- non tocca stato, quantita' di seme, lotto, protocollo, raccolte, stock, allocazioni, ordini, piani.

Per ogni semina, in una sola transazione: UPDATE con CAS su versione (+1) e audit SEMINA/UPDATE con before/after.
Usa un cursore DB-API (psycopg, ``%s``); non fa commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from ...application.production_planning.in_progress_authority import (
    DEFAULT_WINDOW_DAYS, InProgressAuthority, derive_in_progress_authority,
)


class SeminaPredictiveAuthorityError(ValueError):
    """Pre-condizione non soddisfatta: nulla e' stato scritto."""


@dataclass(frozen=True)
class SeminaCandidate:
    public_id: str
    pk: int
    version: int
    state: str
    variety: str
    started_at: datetime
    seed_grams: Decimal
    grams_per_set: Decimal
    protocol: str
    expected_yield: Decimal
    yield_uom: str
    germination_days: int
    light_days: int
    buffer_minutes: int
    harvested_sets: Decimal
    filled: tuple  # (quantita, uom, inizio, fine) oppure (None, None, None, None)

    @property
    def is_filled(self) -> bool:
        return all(value is not None for value in self.filled)

    @property
    def proposed_sets(self) -> int | None:
        """Intero proposto SOLO se i grammi corrispondono esattamente a N SET del protocollo."""
        if self.grams_per_set <= 0:
            return None
        ratio = self.seed_grams / self.grams_per_set
        rounded = ratio.to_integral_value()
        return int(rounded) if rounded >= 1 and ratio == rounded else None


READ_SQL = """
SELECT s.public_id, s.id, s.version, s.stato::text, v.denominazione, s.data_avvio, s.quantita_seme,
       pv.grammi_seme_per_set, pv.public_id, pv.resa_attesa, pv.resa_unita_misura::text,
       pv.germinazione_giorni, pv.crescita_luce_giorni, pv.buffer_temporale_minuti,
       COALESCE((SELECT SUM(rc.quantita) FROM tpo.raccolte rc
                 WHERE rc.semina_id=s.id AND rc.unita_misura='SET'),0),
       s.expected_useful_quantity, s.expected_useful_uom::text, s.harvest_window_start, s.harvest_window_end
FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
JOIN tpo.protocollo_versioni pv ON pv.id=s.protocollo_versione_id
WHERE s.stato<>'CHIUSA' AND s.unita_misura='GRAM'"""


def read(cursor: Any, public_ids: tuple[str, ...] | None = None, *, lock: bool = False) -> tuple[SeminaCandidate, ...]:
    sql = READ_SQL + (" AND s.public_id = ANY(%s)" if public_ids is not None else "") + " ORDER BY v.denominazione, s.data_avvio, s.public_id"
    if lock:
        sql += " FOR UPDATE OF s"
    cursor.execute(sql, (list(public_ids),) if public_ids is not None else ())
    rows = cursor.fetchall()
    return tuple(
        SeminaCandidate(r[0], r[1], int(r[2]), r[3], r[4], r[5], Decimal(r[6]), Decimal(r[7]), r[8], Decimal(r[9]),
                        r[10], int(r[11]), int(r[12]), int(r[13] or 0), Decimal(r[14]),
                        (None if r[15] is None else Decimal(r[15]), r[16], r[17], r[18]))
        for r in rows)


def derive(candidate: SeminaCandidate, sets: int, window_days: int = DEFAULT_WINDOW_DAYS) -> InProgressAuthority:
    authority = derive_in_progress_authority(
        declared_sets=sets, expected_yield=candidate.expected_yield, yield_uom=candidate.yield_uom,
        started_at=candidate.started_at, germination_days=candidate.germination_days,
        light_days=candidate.light_days, buffer_minutes=candidate.buffer_minutes, window_days=window_days)
    if authority is None:
        raise SeminaPredictiveAuthorityError(
            f"{candidate.public_id}: impossibile derivare (resa del protocollo in {candidate.yield_uom}, "
            f"SET dichiarati {sets}). Servono SET interi >= 1 e resa del protocollo in SET.")
    return authority


def _same(candidate: SeminaCandidate, authority: InProgressAuthority) -> bool:
    quantity, uom, start, end = candidate.filled
    return (quantity == authority.quantity and uom == authority.uom
            and start == authority.window_start and end == authority.window_end)


def plan(cursor: Any, declared: dict[str, int], *, exclude: tuple[str, ...] = (),
         window_days: int = DEFAULT_WINDOW_DAYS):
    """Per ogni semina non chiusa non esclusa: (candidato, sets o None, autorita' o None, stato)."""
    out = []
    for item in read(cursor):
        if item.public_id in exclude:
            continue
        sets = declared.get(item.public_id, item.proposed_sets)
        if item.is_filled:
            out.append((item, sets, None, "GIA_COMPILATA"))
            continue
        if sets is None:
            out.append((item, None, None, "SERVE_SET"))
            continue
        if item.harvested_sets > sets:
            out.append((item, sets, None, "INCOERENTE_RACCOLTO_OLTRE_SET"))
            continue
        try:
            out.append((item, sets, derive(item, sets, window_days), "DA_COMPILARE"))
        except SeminaPredictiveAuthorityError:
            out.append((item, sets, None, "NON_DERIVABILE"))
    return out


def commission_predictive(cursor: Any, *, declared_sets: dict[str, int], actor: str, reason: str,
                          correlation_id: str, provenance: str, window_days: int = DEFAULT_WINDOW_DAYS):
    for name, value in (("actor", actor), ("reason", reason),
                        ("correlation_id", correlation_id), ("provenance", provenance)):
        if not value or not value.strip():
            raise SeminaPredictiveAuthorityError(f"{name} obbligatorio.")
    if not declared_sets:
        raise SeminaPredictiveAuthorityError("Nessuna semina indicata.")
    for public_id, sets in declared_sets.items():
        if isinstance(sets, bool) or not isinstance(sets, int) or sets < 1:
            raise SeminaPredictiveAuthorityError(f"{public_id}: i SET sono un intero >= 1 (dichiarati {sets!r}).")
    found = {item.public_id: item for item in read(cursor, tuple(sorted(declared_sets)), lock=True)}
    missing = sorted(set(declared_sets) - set(found))
    if missing:
        raise SeminaPredictiveAuthorityError(f"Semine inesistenti o chiuse: {', '.join(missing)}")
    done, replays = [], []
    for public_id in sorted(declared_sets):
        item, sets = found[public_id], declared_sets[public_id]
        authority = derive(item, sets, window_days)
        if item.harvested_sets > sets:
            raise SeminaPredictiveAuthorityError(
                f"{public_id}: gia' raccolti {item.harvested_sets} SET, piu' dei {sets} dichiarati.")
        if item.is_filled:
            if _same(item, authority):
                replays.append(public_id)
                continue
            raise SeminaPredictiveAuthorityError(
                f"{public_id}: autorita' predittiva gia' compilata con valori diversi; la correzione "
                "richiede una decisione separata (non supportata da questo comando).")
        cursor.execute(
            """UPDATE tpo.semine SET expected_useful_quantity=%s,expected_useful_uom=%s,
                      harvest_window_start=%s,harvest_window_end=%s,version=version+1
               WHERE id=%s AND version=%s AND stato<>'CHIUSA' AND expected_useful_quantity IS NULL
                 AND expected_useful_uom IS NULL AND harvest_window_start IS NULL AND harvest_window_end IS NULL
               RETURNING version""",
            (authority.quantity, authority.uom, authority.window_start, authority.window_end, item.pk, item.version))
        if cursor.fetchone() != (item.version + 1,):
            raise SeminaPredictiveAuthorityError(f"{public_id}: CAS fallita, riprovare.")
        cursor.execute(
            """INSERT INTO tpo.audit_eventi
                 (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                  before_data,after_data,correlation_id,provenance)
               VALUES (CURRENT_TIMESTAMP,%s,'SEMINA',%s,'UPDATE',%s,%s,%s,%s,%s)""",
            (actor, public_id, reason,
             Jsonb({"expected_useful_quantity": None, "expected_useful_uom": None,
                    "harvest_window_start": None, "harvest_window_end": None, "version": item.version}),
             Jsonb({"expected_useful_quantity": str(authority.quantity), "expected_useful_uom": authority.uom,
                    "harvest_window_start": authority.window_start.isoformat(),
                    "harvest_window_end": authority.window_end.isoformat(), "version": item.version + 1,
                    "declared_sets": sets, "protocol_version": item.protocol,
                    "seed_grams": str(item.seed_grams), "window_days": window_days,
                    "derivation": "SET dichiarati x resa protocollo; avvio + germinazione + luce + buffer"}),
             correlation_id, provenance))
        done.append(public_id)
    return tuple(done), tuple(replays)
