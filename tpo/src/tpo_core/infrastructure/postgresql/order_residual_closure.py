"""Chiusura governata del RESIDUO NON PIU' DOVUTO di ordini parzialmente evasi.

Addendum 5/10/2026 (Owner: Matteo: "residuo non piu' dovuto"). Un ordine PARZIALMENTE_EVASO scaduto
non puo' essere ANNULLATO (ha consegne: ``ct_ordini_fulfilment_state``) e non puo' essere EVASO finche'
la quantita' ordinata supera quella consegnata. Se il cliente non deve piu' ricevere il residuo, la
chiusura onesta e' emendare la quantita' ordinata di ogni riga a quella effettivamente consegnata.

Per ogni ordine, in una sola transazione:
- ``righe_ordine.quantita`` = quantita' consegnata (CAS su versione, +1) + audit RIGA_ORDINE con
  la quantita' ORIGINALE ordinata nel ``before_data`` (nulla va perso);
- ``ordini.stato`` PARZIALMENTE_EVASO -> EVASO (CAS, +1) + audit STATE_TRANSITION: ora e' coerente
  con le consegne registrate (il database lo verifica a fine transazione);
- ogni allocazione ATTIVA sulle sue righe viene RILASCIATA (append-only + audit).

Non tocca consegne, righe di consegna, stock, semine, movimenti, fatture, programmi di fornitura.

Rifiuta: ordini non PARZIALMENTE_EVASO, con consegne non ancora CONSEGNATE, con righe mai consegnate
(la quantita' non puo' diventare 0: quel pezzo andrebbe annullato, non emendato), senza residuo.

Usa un cursore DB-API (psycopg, ``%s``); non fa commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from .order_cancellation import allocations_to_release, unsafe_harvest_allocations


class OrderResidualClosureError(ValueError):
    """Pre-condizione non soddisfatta: nulla e' stato scritto."""


@dataclass(frozen=True)
class LineResidual:
    public_id: str
    pk: int
    version: int
    position: int
    variety: str
    ordered: Decimal
    delivered: Decimal
    unit: str

    @property
    def residual(self) -> Decimal:
        return self.ordered - self.delivered


@dataclass(frozen=True)
class OrderResidual:
    public_id: str
    pk: int
    version: int
    state: str
    customer: str
    delivery_date: object
    pending_deliveries: int
    lines: tuple[LineResidual, ...]


def read(cursor: Any, order_public_ids: tuple[str, ...]) -> tuple[OrderResidual, ...]:
    cursor.execute(
        """SELECT o.public_id,o.id,o.version,o.stato::text,cl.denominazione,o.data_consegna_prevista,
                  (SELECT count(*) FROM tpo.consegne_ordini co JOIN tpo.consegne c ON c.id=co.consegna_id
                    WHERE co.ordine_id=o.id AND c.stato<>'CONSEGNATA')
           FROM tpo.ordini o JOIN tpo.clienti cl ON cl.id=o.cliente_id
           WHERE o.public_id = ANY(%s) ORDER BY o.public_id""", (list(order_public_ids),))
    orders = cursor.fetchall()
    result = []
    for row in orders:
        cursor.execute(
            """SELECT ro.public_id,ro.id,ro.version,ro.posizione,v.denominazione,ro.quantita,
                      COALESCE(SUM(rc.quantita) FILTER (WHERE c.stato='CONSEGNATA'),0),ro.unita_misura::text
               FROM tpo.righe_ordine ro JOIN tpo.varieta v ON v.id=ro.varieta_id
               LEFT JOIN tpo.righe_consegna rc ON rc.riga_ordine_id=ro.id
               LEFT JOIN tpo.consegne c ON c.id=rc.consegna_id
               WHERE ro.ordine_id=%s GROUP BY ro.id,v.denominazione ORDER BY ro.posizione""", (row[1],))
        lines = tuple(LineResidual(r[0], r[1], int(r[2]), int(r[3]), r[4], Decimal(r[5]), Decimal(r[6]), r[7])
                      for r in cursor.fetchall())
        result.append(OrderResidual(row[0], row[1], int(row[2]), row[3], row[4], row[5], int(row[6]), lines))
    return tuple(result)


def _problem(order: OrderResidual) -> str | None:
    if order.state != "PARZIALMENTE_EVASO":
        return f"stato {order.state} (serve PARZIALMENTE_EVASO)"
    if order.pending_deliveries:
        return "ha consegne non ancora CONSEGNATE"
    if not order.lines or all(line.residual <= 0 for line in order.lines):
        return "nessun residuo da chiudere"
    if any(line.public_id is None for line in order.lines):
        return "righe senza identificativo pubblico (RO-): assegnarlo prima"
    never = [line.public_id for line in order.lines if line.delivered <= 0]
    if never:
        return ("righe mai consegnate (" + ", ".join(never) + "): la quantita' non puo' diventare 0, "
                "serve una decisione diversa")
    return None


def _validated(cursor: Any, ids: tuple[str, ...]) -> tuple[OrderResidual, ...]:
    found = read(cursor, ids)
    missing = sorted(set(ids) - {item.public_id for item in found})
    if missing:
        raise OrderResidualClosureError(f"Ordini inesistenti: {', '.join(missing)}")
    for item in found:
        problem = _problem(item)
        if problem:
            raise OrderResidualClosureError(f"{item.public_id} non chiudibile: {problem}.")
    return found


def preview(cursor: Any, order_public_ids: tuple[str, ...]):
    found = _validated(cursor, tuple(sorted(set(order_public_ids))))
    return found, allocations_to_release(cursor, tuple(item.pk for item in found))


def close_residual(cursor: Any, *, order_public_ids: tuple[str, ...], actor: str, reason: str,
                   correlation_id: str, provenance: str):
    for name, value in (("actor", actor), ("reason", reason),
                        ("correlation_id", correlation_id), ("provenance", provenance)):
        if not value or not value.strip():
            raise OrderResidualClosureError(f"{name} obbligatorio.")
    if not order_public_ids:
        raise OrderResidualClosureError("Nessun ordine indicato.")
    orders = _validated(cursor, tuple(sorted(set(order_public_ids))))
    allocations = allocations_to_release(cursor, tuple(item.pk for item in orders), lock=True)
    unsafe = unsafe_harvest_allocations(allocations)
    if unsafe:
        raise OrderResidualClosureError(
            "Allocazioni RACCOLTA su raccolte non interamente caricate a stock (rilasciarle le "
            "renderebbe di nuovo disponibili): " + ", ".join(f"{a.public_id} ({a.source})" for a in unsafe)
            + ". Serve una decisione esplicita.")
    for item in allocations:
        if item.remaining <= 0:
            raise OrderResidualClosureError(f"{item.public_id} attiva ma senza residuo: dati incoerenti.")
        cursor.execute(
            """INSERT INTO tpo.transizioni_allocazione
                 (allocation_id,transition_type,quantity,replacement_allocation_id,
                  expected_allocation_version,created_by,reason,provenance)
               VALUES (%s,'RILASCIATA',%s,NULL,%s,%s,%s,%s)""",
            (item.pk, item.remaining, item.version, actor, reason, provenance))
        cursor.execute(
            """UPDATE tpo.allocazioni SET state='RILASCIATA',version=version+1,
                      updated_at=CURRENT_TIMESTAMP,updated_by=%s
               WHERE id=%s AND state='ATTIVA' AND version=%s RETURNING version""",
            (actor, item.pk, item.version))
        if cursor.fetchone() != (item.version + 1,):
            raise OrderResidualClosureError(f"{item.public_id}: CAS fallita, riprovare.")
        _audit(cursor, actor, "ALLOCAZIONE", item.public_id, "STATE_TRANSITION", reason,
               {"remaining": str(item.remaining), "state": "ATTIVA"},
               {"remaining": "0", "state": "RILASCIATA"}, correlation_id, provenance)
    for order in orders:
        for line in order.lines:
            cursor.execute(
                """UPDATE tpo.righe_ordine SET quantita=%s,version=version+1
                   WHERE id=%s AND version=%s RETURNING version""",
                (line.delivered, line.pk, line.version))
            if cursor.fetchone() != (line.version + 1,):
                raise OrderResidualClosureError(f"{line.public_id}: CAS fallita, riprovare.")
            _audit(cursor, actor, "RIGA_ORDINE", line.public_id, "UPDATE", reason,
                   {"order": order.public_id, "variety": line.variety, "ordered": str(line.ordered),
                    "delivered": str(line.delivered), "unit": line.unit, "version": line.version},
                   {"order": order.public_id, "variety": line.variety, "ordered": str(line.delivered),
                    "residual_waived": str(line.residual), "unit": line.unit, "version": line.version + 1},
                   correlation_id, provenance)
        cursor.execute(
            """UPDATE tpo.ordini SET stato='EVASO',version=version+1
               WHERE id=%s AND stato='PARZIALMENTE_EVASO' AND version=%s RETURNING version""",
            (order.pk, order.version))
        if cursor.fetchone() != (order.version + 1,):
            raise OrderResidualClosureError(f"{order.public_id}: CAS fallita, riprovare.")
        _audit(cursor, actor, "ORDINE", order.public_id, "STATE_TRANSITION", reason,
               {"public_id": order.public_id, "state": "PARZIALMENTE_EVASO", "version": order.version},
               {"public_id": order.public_id, "state": "EVASO", "version": order.version + 1},
               correlation_id, provenance)
    return orders, allocations


def _audit(cursor, actor, entity_type, public_id, operation, reason, before, after, correlation_id, provenance):
    cursor.execute(
        """INSERT INTO tpo.audit_eventi
             (occurred_at,actor,entity_type,entity_public_id,operation,reason,
              before_data,after_data,correlation_id,provenance)
           VALUES (CURRENT_TIMESTAMP,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (actor, entity_type, public_id, operation, reason, Jsonb(before), Jsonb(after),
         correlation_id, provenance))
