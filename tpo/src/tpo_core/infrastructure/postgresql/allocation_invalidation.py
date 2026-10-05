"""Invalidazione governata di allocazioni STOCK obsolete.

Addendum 5/10/2026 (Owner: Matteo). Quando merce a magazzino esce fuori
sistema (venduta, scartata) senza che la consegna sia registrata, lo STOCK
scende sotto le allocazioni attive del piano e ogni nuovo planning si ferma con
RESOURCE_OVERALLOCATED. Questa operazione chiude SOLO le allocazioni indicate:

- una riga ``transizioni_allocazione`` INVALIDA (append-only) per l'intero residuo;
- ``allocazioni.state='INVALIDA'`` con CAS su versione (+1);
- un evento ``audit_eventi`` STATE_TRANSITION per allocazione.

Non crea revisioni di piano, non tocca ordini, righe d'ordine, stock, semine
ne' movimenti. E' consentita solo per allocazioni STOCK ATTIVE realmente
sovra-allocate (stock disponibile < somma delle allocazioni STOCK attive della
stessa risorsa): mai su un'allocazione ancora coperta da merce.

Usa un cursore DB-API (psycopg, ``%s``); non fa commit: la transazione e' del
chiamante (tutto o niente).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

_TERMINAL = ("CONSUMATA", "RILASCIATA", "SOSTITUITA", "INVALIDA")


class AllocationInvalidationError(ValueError):
    """Pre-condizione non soddisfatta: nulla e' stato scritto."""


@dataclass(frozen=True)
class AllocationInvalidationCandidate:
    public_id: str
    version: int
    allocation_type: str
    quantity: Decimal
    remaining: Decimal
    unit: str
    state: str
    order_line: str
    order: str
    revision: str
    variety: str
    stock_available: Decimal | None
    stock_active_allocated: Decimal | None

    @property
    def stale(self) -> bool:
        return (
            self.state == "ATTIVA" and self.allocation_type == "STOCK"
            and self.stock_available is not None
            and self.stock_active_allocated is not None
            and self.stock_available < self.stock_active_allocated
        )


def read_candidates(cursor: Any, allocation_public_ids: tuple[str, ...],
                    *, lock: bool = False) -> tuple[AllocationInvalidationCandidate, ...]:
    cursor.execute(
        f"""SELECT a.public_id,a.version,a.allocation_type,a.quantity,
                  a.quantity - COALESCE((SELECT SUM(t.quantity)
                       FROM tpo.transizioni_allocazione t
                       WHERE t.allocation_id=a.id AND t.transition_type IN
                             ('CONSUMATA','RILASCIATA','SOSTITUITA','INVALIDA')),0),
                  a.unita_misura::text,a.state,ro.public_id,o.public_id,pr.public_id,
                  v.public_id,st.disponibile,
                  (SELECT COALESCE(SUM(a2.quantity - COALESCE((SELECT SUM(t2.quantity)
                         FROM tpo.transizioni_allocazione t2
                         WHERE t2.allocation_id=a2.id),0)),0)
                     FROM tpo.allocazioni a2
                     JOIN tpo.allocazioni_stock s2 ON s2.allocation_id=a2.id
                    WHERE a2.state='ATTIVA'
                      AND s2.stock_varieta_id=ast.stock_varieta_id
                      AND s2.stock_unita_misura=ast.stock_unita_misura)
           FROM tpo.allocazioni a
           JOIN tpo.righe_piano_semina rps ON rps.id=a.riga_piano_semina_id
           JOIN tpo.piano_produzione_revisioni pr ON pr.id=rps.piano_revisione_id
           JOIN tpo.righe_ordine ro ON ro.id=rps.riga_ordine_id
           JOIN tpo.ordini o ON o.id=ro.ordine_id
           JOIN tpo.varieta v ON v.id=ro.varieta_id
           LEFT JOIN tpo.allocazioni_stock ast ON ast.allocation_id=a.id
           LEFT JOIN tpo.stock st ON st.varieta_id=ast.stock_varieta_id
                                 AND st.unita_misura=ast.stock_unita_misura
           WHERE a.public_id = ANY(%s) ORDER BY a.public_id
           {'FOR UPDATE OF a' if lock else ''}""",
        (list(allocation_public_ids),),
    )
    rows = cursor.fetchall()
    return tuple(
        AllocationInvalidationCandidate(
            r[0], int(r[1]), r[2], Decimal(r[3]), Decimal(r[4]), r[5], r[6], r[7], r[8],
            r[9], r[10],
            None if r[11] is None else Decimal(r[11]),
            None if r[12] is None else Decimal(r[12]),
        ) for r in rows
    )


def _validated(cursor: Any, ids: tuple[str, ...], *, lock: bool):
    found = read_candidates(cursor, ids, lock=lock)
    missing = sorted(set(ids) - {item.public_id for item in found})
    if missing:
        raise AllocationInvalidationError(f"Allocazioni inesistenti: {', '.join(missing)}")
    for item in found:
        if item.state != "ATTIVA":
            raise AllocationInvalidationError(f"{item.public_id} non e' ATTIVA (stato {item.state}).")
        if item.allocation_type != "STOCK":
            raise AllocationInvalidationError(f"{item.public_id} non e' di tipo STOCK.")
        if item.remaining <= 0:
            raise AllocationInvalidationError(f"{item.public_id} non ha residuo.")
        if not item.stale:
            raise AllocationInvalidationError(
                f"{item.public_id} non e' obsoleta: lo stock disponibile "
                f"({item.stock_available}) copre ancora le allocazioni attive "
                f"({item.stock_active_allocated})."
            )
    # Mai piu' del necessario: per ogni risorsa lo scoperto e' allocato-disponibile.
    excess: dict[tuple[str, str], Decimal] = {}
    for item in found:
        key = (item.variety, item.unit)
        excess[key] = excess.get(key, Decimal("0")) + item.remaining
    for item in found:
        key = (item.variety, item.unit)
        shortfall = item.stock_active_allocated - item.stock_available
        if excess[key] > shortfall:
            raise AllocationInvalidationError(
                f"Invalidare {excess[key]} {item.unit} di {item.variety} supera lo scoperto reale "
                f"({shortfall}): resterebbe stock libero invalidato senza motivo."
            )
    return found


def preview(cursor: Any, allocation_public_ids: tuple[str, ...]):
    return _validated(cursor, tuple(sorted(set(allocation_public_ids))), lock=False)


def invalidate(
    cursor: Any, *, allocation_public_ids: tuple[str, ...], actor: str, reason: str,
    correlation_id: str, provenance: str,
) -> tuple[AllocationInvalidationCandidate, ...]:
    for name, value in (("actor", actor), ("reason", reason),
                        ("correlation_id", correlation_id), ("provenance", provenance)):
        if not value or not value.strip():
            raise AllocationInvalidationError(f"{name} obbligatorio.")
    if not allocation_public_ids:
        raise AllocationInvalidationError("Nessuna allocazione indicata.")
    ids = tuple(sorted(set(allocation_public_ids)))
    found = _validated(cursor, ids, lock=True)
    for item in found:
        cursor.execute(
            """INSERT INTO tpo.transizioni_allocazione
                 (allocation_id,transition_type,quantity,replacement_allocation_id,
                  expected_allocation_version,created_by,reason,provenance)
               SELECT id,'INVALIDA',%s,NULL,%s,%s,%s,%s FROM tpo.allocazioni
               WHERE public_id=%s""",
            (item.remaining, item.version, actor, reason, provenance, item.public_id),
        )
        cursor.execute(
            """UPDATE tpo.allocazioni
               SET state='INVALIDA',version=version+1,updated_at=CURRENT_TIMESTAMP,updated_by=%s
               WHERE public_id=%s AND state='ATTIVA' AND version=%s RETURNING version""",
            (actor, item.public_id, item.version),
        )
        if cursor.fetchone() != (item.version + 1,):
            raise AllocationInvalidationError(f"{item.public_id}: CAS fallita, riprovare.")
        cursor.execute(
            """INSERT INTO tpo.audit_eventi
                 (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                  before_data,after_data,correlation_id,provenance)
               VALUES (CURRENT_TIMESTAMP,%s,'ALLOCAZIONE',%s,'STATE_TRANSITION',%s,%s,%s,%s,%s)""",
            (actor, item.public_id, reason,
             Jsonb({"remaining": str(item.remaining), "state": "ATTIVA"}),
             Jsonb({"remaining": "0", "state": "INVALIDA"}),
             correlation_id, provenance),
        )
    return found
