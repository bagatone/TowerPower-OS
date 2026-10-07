"""Modifica governata di UN ordine APERTO (quantita' di una riga, data di consegna prevista).

Addendum 7/10/2026 (Owner: Matteo: "un comando per modificare gli ordini senza fare tutto sto casino ogni
volta; teniamo l'originale"). Complementare ad ``order_cancellation`` (annullare un ordine intero) e a
``order_residual_closure`` (residuo di ordini parzialmente evasi): qui l'ordine resta APERTO e cambia solo
quello che il cliente ha davvero chiesto.

Per ogni modifica, in una sola transazione:
- la riga (``righe_ordine.quantita``) o l'ordine (``ordini.data_consegna_prevista``) viene aggiornata con CAS
  sulla versione (+1): due modifiche concorrenti non si sovrascrivono;
- audit ``RIGA_ORDINE`` / ``ORDINE`` con il valore ORIGINALE in ``before_data`` e ``amended_from`` in
  ``after_data`` (l'originale non si perde mai) e il motivo dichiarato;
- le allocazioni ATTIVE interessate (quelle della riga, o di tutto l'ordine per la data) vengono RILASCIATE
  (append-only + audit): erano calcolate sulla quantita'/data vecchie, il prossimo piano le ricalcola.

Rifiuta: ordini non APERTI, con qualsiasi consegna, quantita' <= 0 o uguale all'attuale, data anteriore alla
data d'ordine, data gia' occupata da un altro ordine dello stesso programma di fornitura, allocazioni RACCOLTA
su raccolte non interamente caricate a stock.

Non tocca stock, semine, movimenti, consegne, fatture, programmi di fornitura. Il programma di fornitura NON viene
modificato: la modifica vale solo per questo ordine.

Usa un cursore DB-API (psycopg, ``%s``); non fa commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from .order_cancellation import AllocationToRelease, allocations_to_release, unsafe_harvest_allocations


class OrderAmendmentError(ValueError):
    """Pre-condizione non soddisfatta: nulla e' stato scritto."""


@dataclass(frozen=True)
class AmendLine:
    public_id: str | None
    pk: int
    version: int
    position: int
    variety: str
    quantity: Decimal
    unit: str


@dataclass(frozen=True)
class AmendOrder:
    public_id: str
    pk: int
    version: int
    state: str
    customer: str
    program: str | None
    order_date: date
    delivery_date: date | None
    creation_type: str
    delivery_rows: int
    lines: tuple[AmendLine, ...]


def read_order(cursor: Any, order_public_id: str, *, lock: bool = False) -> AmendOrder:
    cursor.execute(
        f"""SELECT o.public_id,o.id,o.version,o.stato::text,cl.denominazione,pf.public_id,o.data_ordine,
                   o.data_consegna_prevista,o.tipo_creazione::text,
                   (SELECT count(*) FROM tpo.righe_ordine ro JOIN tpo.righe_consegna rc ON rc.riga_ordine_id=ro.id
                     WHERE ro.ordine_id=o.id)
                   + (SELECT count(*) FROM tpo.consegne_ordini co WHERE co.ordine_id=o.id)
            FROM tpo.ordini o JOIN tpo.clienti cl ON cl.id=o.cliente_id
            LEFT JOIN tpo.programmi_fornitura pf ON pf.id=o.programma_fornitura_id
            WHERE o.public_id=%s {'FOR UPDATE OF o' if lock else ''}""", (order_public_id,))
    row = cursor.fetchone()
    if row is None:
        raise OrderAmendmentError(f"Ordine inesistente: {order_public_id}")
    cursor.execute(
        """SELECT ro.public_id,ro.id,ro.version,ro.posizione,v.denominazione,ro.quantita,ro.unita_misura::text
           FROM tpo.righe_ordine ro JOIN tpo.varieta v ON v.id=ro.varieta_id
           WHERE ro.ordine_id=%s ORDER BY ro.posizione""", (row[1],))
    lines = tuple(AmendLine(r[0], r[1], int(r[2]), int(r[3]), r[4], Decimal(r[5]), r[6]) for r in cursor.fetchall())
    return AmendOrder(row[0], row[1], int(row[2]), row[3], row[4], row[5], row[6], row[7], row[8], int(row[9]), lines)


def _require_editable(order: AmendOrder) -> None:
    if order.state != "APERTO":
        raise OrderAmendmentError(f"{order.public_id}: stato {order.state} (si modifica solo un ordine APERTO).")
    if order.delivery_rows:
        raise OrderAmendmentError(
            f"{order.public_id}: ha consegne registrate; per il residuo non dovuto usa la chiusura del residuo.")


def _fold(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").strip()


def find_line(order: AmendOrder, selector: str) -> AmendLine:
    """Riga per identificativo RO-... oppure per nome varieta' (senza accenti/maiuscole); deve essere una sola."""
    if selector.upper().startswith("RO-"):
        matches = [line for line in order.lines if line.public_id == selector.upper()]
    else:
        matches = [line for line in order.lines if _fold(line.variety) == _fold(selector)]
    if len(matches) != 1:
        names = ", ".join(f"{line.public_id} {line.variety} {line.quantity.normalize():f} {line.unit}" for line in order.lines)
        raise OrderAmendmentError(
            f"{order.public_id}: la riga '{selector}' non individua UNA riga (trovate {len(matches)}). Righe: {names}")
    return matches[0]


def _validated_quantity(order: AmendOrder, line: AmendLine, new_quantity: Decimal) -> None:
    _require_editable(order)
    if new_quantity <= 0:
        raise OrderAmendmentError("La quantita' deve essere maggiore di 0 (per togliere tutto, annulla l'ordine).")
    if new_quantity == line.quantity:
        raise OrderAmendmentError(f"{line.public_id}: la quantita' e' gia' {line.quantity.normalize():f}.")
    if line.public_id is None:
        raise OrderAmendmentError(f"riga {line.position} di {order.public_id} senza identificativo RO-.")


def preview_quantity(cursor: Any, order_public_id: str, selector: str, new_quantity: Decimal
                     ) -> tuple[AmendOrder, AmendLine, tuple[AllocationToRelease, ...]]:
    order = read_order(cursor, order_public_id)
    line = find_line(order, selector)
    _validated_quantity(order, line, new_quantity)
    return order, line, allocations_to_release(cursor, (order.pk,), line_pks=(line.pk,))


def _validated_date(cursor: Any, order: AmendOrder, new_date: date) -> None:
    _require_editable(order)
    if new_date == order.delivery_date:
        raise OrderAmendmentError(f"{order.public_id}: la consegna prevista e' gia' {new_date}.")
    if new_date < order.order_date:
        raise OrderAmendmentError(f"La consegna {new_date} precede la data d'ordine {order.order_date}.")
    if order.program:
        cursor.execute(
            """SELECT o2.public_id FROM tpo.ordini o2
               JOIN tpo.programmi_fornitura pf ON pf.id=o2.programma_fornitura_id
               WHERE pf.public_id=%s AND o2.data_consegna_prevista=%s AND o2.id<>%s AND o2.stato<>'ANNULLATO'""",
            (order.program, new_date, order.pk))
        clash = [r[0] for r in cursor.fetchall()]
        if clash:
            raise OrderAmendmentError(
                f"Il programma {order.program} ha gia' un ordine con consegna {new_date}: {', '.join(clash)}.")


def preview_date(cursor: Any, order_public_id: str, new_date: date
                 ) -> tuple[AmendOrder, tuple[AllocationToRelease, ...]]:
    order = read_order(cursor, order_public_id)
    _validated_date(cursor, order, new_date)
    return order, allocations_to_release(cursor, (order.pk,))


def _check_safe(allocations: tuple[AllocationToRelease, ...]) -> None:
    unsafe = unsafe_harvest_allocations(allocations)
    if unsafe:
        raise OrderAmendmentError(
            "Allocazioni RACCOLTA su raccolte non interamente caricate a stock (rilasciarle le renderebbe di "
            "nuovo disponibili): " + ", ".join(f"{a.public_id} ({a.source})" for a in unsafe)
            + ". Serve una decisione esplicita.")


def _release(cursor: Any, allocations, actor, reason, correlation_id, provenance) -> None:
    for item in allocations:
        if item.remaining <= 0:
            raise OrderAmendmentError(f"{item.public_id} attiva ma senza residuo: dati incoerenti.")
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
            raise OrderAmendmentError(f"{item.public_id}: CAS fallita, riprovare.")
        _audit(cursor, actor, "ALLOCAZIONE", item.public_id, "STATE_TRANSITION", reason,
               {"remaining": str(item.remaining), "state": "ATTIVA"},
               {"remaining": "0", "state": "RILASCIATA"}, correlation_id, provenance)


def _require_text(**values: str) -> None:
    for name, value in values.items():
        if not value or not value.strip():
            raise OrderAmendmentError(f"{name} obbligatorio.")


def amend_line_quantity(cursor: Any, *, order_public_id: str, line_selector: str, new_quantity: Decimal,
                        actor: str, reason: str, correlation_id: str, provenance: str):
    _require_text(actor=actor, reason=reason, correlation_id=correlation_id, provenance=provenance)
    order = read_order(cursor, order_public_id, lock=True)
    line = find_line(order, line_selector)
    _validated_quantity(order, line, new_quantity)
    allocations = allocations_to_release(cursor, (order.pk,), lock=True, line_pks=(line.pk,))
    _check_safe(allocations)
    _release(cursor, allocations, actor, reason, correlation_id, provenance)
    cursor.execute(
        """UPDATE tpo.righe_ordine SET quantita=%s,version=version+1
           WHERE id=%s AND version=%s RETURNING version""", (new_quantity, line.pk, line.version))
    if cursor.fetchone() != (line.version + 1,):
        raise OrderAmendmentError(f"{line.public_id}: CAS fallita, riprovare.")
    _audit(cursor, actor, "RIGA_ORDINE", line.public_id, "UPDATE", reason,
           {"order": order.public_id, "variety": line.variety, "ordered": str(line.quantity),
            "unit": line.unit, "version": line.version},
           {"order": order.public_id, "variety": line.variety, "ordered": str(new_quantity),
            "amended_from": str(line.quantity), "unit": line.unit, "version": line.version + 1},
           correlation_id, provenance)
    return order, line, allocations


def change_delivery_date(cursor: Any, *, order_public_id: str, new_date: date, actor: str, reason: str,
                         correlation_id: str, provenance: str):
    _require_text(actor=actor, reason=reason, correlation_id=correlation_id, provenance=provenance)
    order = read_order(cursor, order_public_id, lock=True)
    _validated_date(cursor, order, new_date)
    allocations = allocations_to_release(cursor, (order.pk,), lock=True)
    _check_safe(allocations)
    _release(cursor, allocations, actor, reason, correlation_id, provenance)
    cursor.execute(
        """UPDATE tpo.ordini SET data_consegna_prevista=%s,version=version+1
           WHERE id=%s AND stato='APERTO' AND version=%s RETURNING version""", (new_date, order.pk, order.version))
    if cursor.fetchone() != (order.version + 1,):
        raise OrderAmendmentError(f"{order.public_id}: CAS fallita, riprovare.")
    _audit(cursor, actor, "ORDINE", order.public_id, "UPDATE", reason,
           {"public_id": order.public_id, "delivery_date": str(order.delivery_date), "version": order.version},
           {"public_id": order.public_id, "delivery_date": str(new_date),
            "amended_from": str(order.delivery_date), "version": order.version + 1},
           correlation_id, provenance)
    return order, allocations


def _audit(cursor, actor, entity_type, public_id, operation, reason, before, after, correlation_id, provenance):
    cursor.execute(
        """INSERT INTO tpo.audit_eventi
             (occurred_at,actor,entity_type,entity_public_id,operation,reason,
              before_data,after_data,correlation_id,provenance)
           VALUES (CURRENT_TIMESTAMP,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (actor, entity_type, public_id, operation, reason, Jsonb(before), Jsonb(after),
         correlation_id, provenance))
