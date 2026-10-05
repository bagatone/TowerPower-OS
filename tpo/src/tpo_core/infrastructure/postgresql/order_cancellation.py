"""Chiusura governata di ORDINI storici scaduti senza consegne (ANNULLATO).

Addendum 5/10/2026 (Owner: Matteo). Gli ordini ricorrenti generati dallo
scheduler prima dell'"avvio pulito" del 3/10 sono rimasti APERTI anche se la
loro data e' passata e nessuna consegna e' mai stata registrata. Il database
ammette EVASO solo con consegne registrate per ogni riga
(``ct_ordini_fulfilment_state``): inventare consegne e' vietato (Regola 1).
L'unica chiusura onesta e' ANNULLATO, con il motivo che dice la verita'.

Per ogni ordine, in una sola transazione:
- ``ordini.stato='ANNULLATO'`` (CAS su versione, +1) + audit STATE_TRANSITION;
- ogni allocazione ATTIVA sulle sue righe (qualsiasi revisione di piano) viene
  RILASCIATA per l'intero residuo (transizione append-only + audit): la
  domanda e' cancellata, nessuna risorsa resta trattenuta.

Rifiuta ordini non APERTI, con qualsiasi consegna (anche non CONSEGNATA) o con
data prevista non anteriore alla soglia. Non tocca stock, semine, movimenti,
consegne, fatture, programmi di fornitura, righe d'ordine.

Usa un cursore DB-API (psycopg, ``%s``); non fa commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb


class OrderCancellationError(ValueError):
    """Pre-condizione non soddisfatta: nulla e' stato scritto."""


@dataclass(frozen=True)
class OrderCandidate:
    public_id: str
    pk: int
    state: str
    version: int
    delivery_date: date | None
    creation_type: str
    customer: str
    program: str | None
    lines: int
    delivery_rows: int
    delivery_links: int


@dataclass(frozen=True)
class AllocationToRelease:
    public_id: str
    pk: int
    version: int
    allocation_type: str
    remaining: Decimal
    unit: str
    order: str
    source: str | None = None          # RACCOLTA: public id della raccolta
    harvest_fully_loaded: bool | None = None   # RACCOLTA: gia' interamente caricata a stock?


def list_open(cursor: Any, order_public_ids: tuple[str, ...] | None = None) -> tuple[OrderCandidate, ...]:
    where = "o.public_id = ANY(%s)" if order_public_ids is not None else \
        "o.stato IN ('APERTO','PARZIALMENTE_EVASO')"
    params = (list(order_public_ids),) if order_public_ids is not None else ()
    cursor.execute(
        f"""SELECT o.public_id,o.id,o.stato::text,o.version,o.data_consegna_prevista,
                   o.tipo_creazione::text,cl.denominazione,pf.public_id,
                   (SELECT count(*) FROM tpo.righe_ordine ro WHERE ro.ordine_id=o.id),
                   (SELECT count(*) FROM tpo.righe_ordine ro
                      JOIN tpo.righe_consegna rc ON rc.riga_ordine_id=ro.id WHERE ro.ordine_id=o.id),
                   (SELECT count(*) FROM tpo.consegne_ordini co WHERE co.ordine_id=o.id)
            FROM tpo.ordini o JOIN tpo.clienti cl ON cl.id=o.cliente_id
            LEFT JOIN tpo.programmi_fornitura pf ON pf.id=o.programma_fornitura_id
            WHERE {where} ORDER BY o.data_consegna_prevista,o.public_id""",
        params,
    )
    return tuple(OrderCandidate(r[0], r[1], r[2], int(r[3]), r[4], r[5], r[6], r[7],
                                int(r[8]), int(r[9]), int(r[10])) for r in cursor.fetchall())


def eligible(cursor: Any, before: date) -> tuple[tuple[OrderCandidate, ...], tuple[OrderCandidate, ...]]:
    """(chiudibili, esclusi): tra gli ordini aperti con consegna prevista < before."""
    ok, skipped = [], []
    for item in list_open(cursor):
        if item.delivery_date is None or item.delivery_date >= before:
            continue
        (ok if _closable(item, before) is None else skipped).append(item)
    return tuple(ok), tuple(skipped)


def _closable(item: OrderCandidate, before: date) -> str | None:
    if item.state != "APERTO":
        return f"stato {item.state} (solo APERTO)"
    if item.delivery_rows or item.delivery_links:
        return "ha consegne registrate"
    if item.lines <= 0:
        return "priva di righe"
    if item.delivery_date is None or item.delivery_date >= before:
        return f"consegna prevista {item.delivery_date} non anteriore a {before}"
    return None


def allocations_to_release(cursor: Any, order_pks: tuple[int, ...], *, lock: bool = False
                           ) -> tuple[AllocationToRelease, ...]:
    cursor.execute(
        f"""SELECT a.public_id,a.id,a.version,a.allocation_type,
                   a.quantity - COALESCE((SELECT SUM(t.quantity)
                        FROM tpo.transizioni_allocazione t
                        WHERE t.allocation_id=a.id AND t.transition_type IN
                              ('CONSUMATA','RILASCIATA','SOSTITUITA','INVALIDA')),0),
                   a.unita_misura::text,o.public_id,
                   rac.public_id,
                   CASE WHEN rac.id IS NULL THEN NULL ELSE
                     COALESCE((SELECT SUM(m.quantita) FROM tpo.movimenti_magazzino m
                               WHERE m.raccolta_id=rac.id AND m.tipo='CARICO'
                                 AND m.unita_misura=rac.unita_misura),0) >= rac.quantita END
            FROM tpo.allocazioni a
            JOIN tpo.righe_piano_semina rps ON rps.id=a.riga_piano_semina_id
            JOIN tpo.righe_ordine ro ON ro.id=rps.riga_ordine_id
            JOIN tpo.ordini o ON o.id=ro.ordine_id
            LEFT JOIN tpo.allocazioni_raccolta ar ON ar.allocation_id=a.id
            LEFT JOIN tpo.raccolte rac ON rac.id=ar.raccolta_id
            WHERE a.state='ATTIVA' AND o.id = ANY(%s)
            ORDER BY a.public_id {'FOR UPDATE OF a' if lock else ''}""",
        (list(order_pks),),
    )
    return tuple(AllocationToRelease(r[0], r[1], int(r[2]), r[3], Decimal(r[4]), r[5], r[6], r[7], r[8])
                 for r in cursor.fetchall())


def unsafe_harvest_allocations(allocations: tuple[AllocationToRelease, ...]) -> tuple[AllocationToRelease, ...]:
    """Allocazioni RACCOLTA la cui raccolta NON e' interamente caricata a stock: rilasciarle
    la renderebbe di nuovo disponibile come merce libera (potrebbe non esistere piu')."""
    return tuple(a for a in allocations if a.allocation_type == "RACCOLTA" and not a.harvest_fully_loaded)


def _validated(cursor: Any, ids: tuple[str, ...], before: date) -> tuple[OrderCandidate, ...]:
    found = list_open(cursor, ids)
    missing = sorted(set(ids) - {item.public_id for item in found})
    if missing:
        raise OrderCancellationError(f"Ordini inesistenti: {', '.join(missing)}")
    for item in found:
        problem = _closable(item, before)
        if problem:
            raise OrderCancellationError(f"{item.public_id} non chiudibile: {problem}.")
    return found


def preview(cursor: Any, order_public_ids: tuple[str, ...], before: date):
    ids = tuple(sorted(set(order_public_ids)))
    found = _validated(cursor, ids, before)
    return found, allocations_to_release(cursor, tuple(item.pk for item in found))


def cancel(cursor: Any, *, order_public_ids: tuple[str, ...], before: date, actor: str, reason: str,
           correlation_id: str, provenance: str):
    for name, value in (("actor", actor), ("reason", reason),
                        ("correlation_id", correlation_id), ("provenance", provenance)):
        if not value or not value.strip():
            raise OrderCancellationError(f"{name} obbligatorio.")
    if not order_public_ids:
        raise OrderCancellationError("Nessun ordine indicato.")
    ids = tuple(sorted(set(order_public_ids)))
    orders = _validated(cursor, ids, before)
    allocations = allocations_to_release(cursor, tuple(item.pk for item in orders), lock=True)
    unsafe = unsafe_harvest_allocations(allocations)
    if unsafe:
        raise OrderCancellationError(
            "Allocazioni RACCOLTA su raccolte non interamente caricate a stock (rilasciarle le "
            "renderebbe di nuovo disponibili): " + ", ".join(f"{a.public_id} ({a.source})" for a in unsafe)
            + ". Serve una decisione esplicita."
        )
    for item in allocations:
        if item.remaining <= 0:
            raise OrderCancellationError(f"{item.public_id} attiva ma senza residuo: dati incoerenti.")
        cursor.execute(
            """INSERT INTO tpo.transizioni_allocazione
                 (allocation_id,transition_type,quantity,replacement_allocation_id,
                  expected_allocation_version,created_by,reason,provenance)
               VALUES (%s,'RILASCIATA',%s,NULL,%s,%s,%s,%s)""",
            (item.pk, item.remaining, item.version, actor, reason, provenance),
        )
        cursor.execute(
            """UPDATE tpo.allocazioni SET state='RILASCIATA',version=version+1,
                      updated_at=CURRENT_TIMESTAMP,updated_by=%s
               WHERE id=%s AND state='ATTIVA' AND version=%s RETURNING version""",
            (actor, item.pk, item.version),
        )
        if cursor.fetchone() != (item.version + 1,):
            raise OrderCancellationError(f"{item.public_id}: CAS fallita, riprovare.")
        cursor.execute(
            """INSERT INTO tpo.audit_eventi
                 (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                  before_data,after_data,correlation_id,provenance)
               VALUES (CURRENT_TIMESTAMP,%s,'ALLOCAZIONE',%s,'STATE_TRANSITION',%s,%s,%s,%s,%s)""",
            (actor, item.public_id, reason,
             Jsonb({"remaining": str(item.remaining), "state": "ATTIVA"}),
             Jsonb({"remaining": "0", "state": "RILASCIATA"}),
             correlation_id, provenance),
        )
    for order in orders:
        cursor.execute(
            """UPDATE tpo.ordini SET stato='ANNULLATO',version=version+1
               WHERE id=%s AND stato='APERTO' AND version=%s RETURNING version""",
            (order.pk, order.version),
        )
        if cursor.fetchone() != (order.version + 1,):
            raise OrderCancellationError(f"{order.public_id}: CAS fallita, riprovare.")
        cursor.execute(
            """INSERT INTO tpo.audit_eventi
                 (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                  before_data,after_data,correlation_id,provenance)
               VALUES (CURRENT_TIMESTAMP,%s,'ORDINE',%s,'STATE_TRANSITION',%s,%s,%s,%s,%s)""",
            (actor, order.public_id, reason,
             Jsonb({"public_id": order.public_id, "state": "APERTO", "version": order.version}),
             Jsonb({"public_id": order.public_id, "state": "ANNULLATO", "version": order.version + 1}),
             correlation_id, provenance),
        )
    return orders, allocations
