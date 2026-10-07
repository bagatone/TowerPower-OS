"""Modifica un ordine APERTO con un solo comando (7/10/2026, richiesta di Matteo: "piu' comodo e funzionale").

Tre operazioni, sempre in ANTEPRIMA finche' non aggiungi --esegui; tutto o niente (una transazione); l'originale
resta nell'audit (before_data) e il motivo e' scritto; le allocazioni interessate vengono rilasciate e il prossimo
piano le ricalcola. Non tocca stock, semine, movimenti, consegne, fatture ne' il programma di fornitura.

  annulla   ORD-000016 [ORD-...]            annulla l'ordine intero (come 2026-10-07_annulla_ordini.py)
  quantita  ORD-000016 Rabano 2             cambia la quantita' di UNA riga (per nome varieta' o RO-000036)
  data      ORD-000016 2026-10-09           sposta la consegna prevista

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-07_modifica_ordine.py quantita ORD-000016 Rabano 2 --motivo "..."
  ... --esegui    per scrivere davvero

Limiti (rifiuta, non scrive): ordini non APERTI o con consegne registrate; quantita' <= 0 (per togliere tutto:
annulla); per togliere UNA sola riga di un ordine a piu' righe serve un cambio di schema (le righe non hanno uno
stato "annullata"), oggi non possibile.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

from src.tpo_core.infrastructure.postgresql.order_amendment import (  # noqa: E402
    OrderAmendmentError, amend_line_quantity, change_delivery_date, preview_date, preview_quantity,
)

ACTOR = "matteo"
PROVENANCE = "commissioning:2026-10-07_modifica_ordine"


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def _allocations(allocations, out) -> None:
    by_type = Counter()
    for item in allocations:
        by_type[(item.allocation_type, item.unit)] += item.remaining
    out(f"\n== ALLOCAZIONI ATTIVE CHE VERRANNO RILASCIATE ({len(allocations)})")
    for (kind, unit), qty in sorted(by_type.items()):
        out(f"  {kind}: {_n(qty)} {unit}")
    out("  (le copie dello stesso ordine in piu' piani si sommano: il prossimo piano le ricalcola)")


def _program_note(order, out) -> None:
    if order.program:
        out(f"\nOrdine del programma {order.program}: il programma NON viene modificato (le prossime consegne "
            "restano come configurate nel programma).")


def run_quantita(conn, order_id: str, selector: str, quantity: Decimal, reason: str, esegui: bool,
                 out=print) -> int:
    cur = conn.cursor()
    try:
        order, line, allocations = preview_quantity(cur, order_id, selector, quantity)
    except OrderAmendmentError as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    out(f"== MODIFICA QUANTITA' ({'ESECUZIONE' if esegui else 'ANTEPRIMA, NULLA VIENE SCRITTO'})")
    out(f"{order.public_id} | {order.customer} | consegna {order.delivery_date} | {order.state}")
    out(f"{line.public_id} {line.variety}: {_n(line.quantity)} {line.unit} -> {_n(quantity)} {line.unit}")
    out("L'originale resta nell'audit (before_data / amended_from).")
    _allocations(allocations, out)
    _program_note(order, out)
    out(f"\nMotivo registrato: {reason}")
    if not esegui:
        conn.rollback()
        out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        return 0
    try:
        _, _, released = amend_line_quantity(
            cur, order_public_id=order_id, line_selector=selector, new_quantity=quantity, actor=ACTOR,
            reason=reason, correlation_id=f"modifica-quantita-{order_id}-{line.public_id}", provenance=PROVENANCE)
        conn.commit()
    except OrderAmendmentError as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: {line.public_id} {line.variety} ora {_n(quantity)} {line.unit}; {len(released)} allocazioni RILASCIATE.")
    return 0


def run_data(conn, order_id: str, new_date: date, reason: str, esegui: bool, out=print) -> int:
    cur = conn.cursor()
    try:
        order, allocations = preview_date(cur, order_id, new_date)
    except OrderAmendmentError as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    out(f"== SPOSTA CONSEGNA ({'ESECUZIONE' if esegui else 'ANTEPRIMA, NULLA VIENE SCRITTO'})")
    out(f"{order.public_id} | {order.customer} | {order.state}")
    out(f"consegna prevista {order.delivery_date} -> {new_date}")
    out("L'originale resta nell'audit (before_data / amended_from).")
    _allocations(allocations, out)
    _program_note(order, out)
    out(f"\nMotivo registrato: {reason}")
    if not esegui:
        conn.rollback()
        out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        return 0
    try:
        _, released = change_delivery_date(
            cur, order_public_id=order_id, new_date=new_date, actor=ACTOR, reason=reason,
            correlation_id=f"modifica-data-{order_id}", provenance=PROVENANCE)
        conn.commit()
    except OrderAmendmentError as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: consegna di {order_id} spostata al {new_date}; {len(released)} allocazioni RILASCIATE.")
    return 0


def run_annulla(conn, order_ids, reason: str | None, esegui: bool, out=print) -> int:
    spec = importlib.util.spec_from_file_location(
        "annulla_ordini", ROOT / "scripts" / "commissioning" / "2026-10-07_annulla_ordini.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.run(conn, order_ids, reason or module.DEFAULT_REASON, esegui, out=out)


def _quantity(text: str) -> Decimal:
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        raise SystemExit(f"STOP: quantita' non valida: {text}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("annulla")
    a1.add_argument("ordini", nargs="+")
    a1.add_argument("--motivo")
    a2 = sub.add_parser("quantita")
    a2.add_argument("ordine")
    a2.add_argument("riga", help="nome varieta' (es. Rabano) oppure RO-000000")
    a2.add_argument("quantita")
    a2.add_argument("--motivo", required=True)
    a3 = sub.add_parser("data")
    a3.add_argument("ordine")
    a3.add_argument("data", help="AAAA-MM-GG")
    a3.add_argument("--motivo", required=True)
    for p in (a1, a2, a3):
        p.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    orders = a.ordini if a.cmd == "annulla" else [a.ordine]
    if not all(o.startswith("ORD-") for o in orders):
        raise SystemExit("STOP: indica ordini nel formato ORD-000000.")
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        if a.cmd == "annulla":
            return run_annulla(conn, a.ordini, a.motivo, a.esegui)
        if a.cmd == "quantita":
            return run_quantita(conn, a.ordine, a.riga, _quantity(a.quantita), a.motivo, a.esegui)
        return run_data(conn, a.ordine, date.fromisoformat(a.data), a.motivo, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
