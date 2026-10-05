"""TEST SUPPORT: authoring of an INVALIDA disposition set (non e' codice di produzione).

Addendum 5/10/2026 (Owner: Matteo). Nessun comando governato crea i disposition
set richiesti dal replanning; questo modulo scrive SOLO l'autorizzazione
(set + decisioni, poi stato AUTHORIZED nella stessa transazione). Non cambia
allocazioni, piani o stock: l'effetto avviene unicamente quando il replanning
governato (``ReplanProductionPlanningCommand``) consuma il set.

Usa un cursore DB-API (psycopg, parametri ``%s``); non fa commit: la
transazione appartiene al chiamante.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.tpo_core.application.production_planning.models import (
    AllocationDispositionDecision, PublicId, disposition_set_key_v1,
)

_INVALIDATION_CAUSES = (
    "SOURCE_UNUSABLE", "SEEDING_FAILED", "HARVEST_UNAVAILABLE",
    "STOCK_QUANTITY_INVALIDATED", "DATA_CORRUPTION_CONFIRMED",
    "MANUAL_INVALIDATION_AUTHORIZED",
)


class DispositionAuthoringError(ValueError):
    """Pre-condizione non soddisfatta: nulla e' stato scritto."""


@dataclass(frozen=True)
class AuthoredDispositionSet:
    decision_set_key: str
    set_id: int
    allocation_public_ids: tuple[str, ...]


def _read_allocations(cursor: Any, revision: str, order_line: str,
                      allocation_public_ids: tuple[str, ...]):
    cursor.execute(
        """SELECT a.id,a.public_id,a.version,a.state,a.allocation_type,a.quantity,
                  a.unita_misura,
                  a.quantity - COALESCE((SELECT SUM(t.quantity)
                       FROM tpo.transizioni_allocazione t
                       WHERE t.allocation_id=a.id
                         AND t.transition_type IN
                             ('CONSUMATA','RILASCIATA','SOSTITUITA','INVALIDA')),0),
                  pr.public_id,ro.public_id
           FROM tpo.allocazioni a
           JOIN tpo.righe_piano_semina rps ON rps.id=a.riga_piano_semina_id
           JOIN tpo.piano_produzione_revisioni pr ON pr.id=rps.piano_revisione_id
           JOIN tpo.righe_ordine ro ON ro.id=rps.riga_ordine_id
           WHERE a.public_id = ANY(%s) ORDER BY a.public_id""",
        (list(allocation_public_ids),),
    )
    rows = cursor.fetchall()
    found = {row[1] for row in rows}
    missing = sorted(set(allocation_public_ids) - found)
    if missing:
        raise DispositionAuthoringError(f"Allocazioni inesistenti: {', '.join(missing)}")
    for row in rows:
        _, public_id, _, state, _, _, _, remaining, rev, line = row
        if state != "ATTIVA":
            raise DispositionAuthoringError(f"{public_id} non e' ATTIVA (stato {state}).")
        if rev != revision or line != order_line:
            raise DispositionAuthoringError(
                f"{public_id} appartiene a {rev}/{line}, non a {revision}/{order_line}."
            )
        if Decimal(remaining) <= 0:
            raise DispositionAuthoringError(f"{public_id} non ha residuo da invalidare.")
    return rows


def author_invalidation_set(
    cursor: Any, *, previous_revision: str, order_line: str, reason_code: str,
    correlation_id: str, allocation_public_ids: tuple[str, ...], cause: str,
    reason: str, provenance: str, authorized_by: str,
) -> AuthoredDispositionSet:
    """Scrive set DRAFT + decisioni INVALIDA/UNUSABLE e lo porta ad AUTHORIZED."""
    if cause not in _INVALIDATION_CAUSES:
        raise DispositionAuthoringError("Causa di invalidazione non ammessa.")
    if not allocation_public_ids:
        raise DispositionAuthoringError("Nessuna allocazione indicata.")
    ids = tuple(sorted(set(allocation_public_ids)))
    rows = _read_allocations(cursor, previous_revision, order_line, ids)
    decisions = tuple(
        AllocationDispositionDecision(
            PublicId(row[1]), int(row[2]), cause, "UNUSABLE", Decimal(row[7]),
            Decimal("0"), "INVALIDA", None, reason, provenance,
        )
        for row in rows
    )
    key = disposition_set_key_v1(
        previous_plan_revision_public_id=PublicId(previous_revision),
        order_line_public_id=PublicId(order_line),
        replanning_reason_code=reason_code, correlation_id=correlation_id,
        decisions=decisions,
    ).value
    cursor.execute(
        """INSERT INTO tpo.replanning_disposition_sets
             (decision_set_key,previous_plan_revision_id,order_line_id,
              replanning_reason_code,correlation_id,state,provenance,created_by)
           SELECT %s,pr.id,ro.id,%s,%s,'DRAFT',%s,%s
           FROM tpo.piano_produzione_revisioni pr, tpo.righe_ordine ro
           WHERE pr.public_id=%s AND ro.public_id=%s RETURNING id""",
        (key, reason_code, correlation_id, provenance, authorized_by,
         previous_revision, order_line),
    )
    created = cursor.fetchone()
    if created is None:
        raise DispositionAuthoringError("Revisione o riga d'ordine inesistente.")
    set_id = created[0]
    for position, (decision, row) in enumerate(zip(decisions, rows), start=1):
        cursor.execute(
            """INSERT INTO tpo.replanning_disposition_decisions
                 (disposition_set_id,position,allocation_id,expected_allocation_version,
                  disposition_cause,source_usability,observed_remaining_quantity,
                  consumed_quantity_delta,target_disposition,reason,provenance)
               VALUES (%s,%s,%s,%s,%s,'UNUSABLE',%s,0,'INVALIDA',%s,%s)""",
            (set_id, position, row[0], decision.expected_version, cause,
             decision.observed_remaining_quantity, reason, provenance),
        )
    cursor.execute(
        """UPDATE tpo.replanning_disposition_sets
           SET state='AUTHORIZED',authorized_at=CURRENT_TIMESTAMP,authorized_by=%s
           WHERE id=%s""",
        (authorized_by, set_id),
    )
    return AuthoredDispositionSet(key, set_id, ids)
