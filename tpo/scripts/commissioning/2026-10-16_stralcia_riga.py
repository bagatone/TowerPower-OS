"""STRALCIO di una o piu' RIGHE da un ordine APERTO a piu' righe, senza migrazione (16/10/2026).

Le righe d'ordine non hanno uno stato "annullata" e non si cancellano (le allocazioni passate le richiamano), quindi
togliere UNA riga si fa cosi', tutto tracciato:
  1. crea un NUOVO ordine manuale, stesso cliente, stessa data d'ordine e di consegna prevista, con le sole righe che restano
     (comando governato `tpo ordine registra-manuale`, idempotente);
  2. annulla l'ordine VECCHIO (ANNULLATO, allocazioni attive rilasciate, motivo "sostituito da ORD-..."). L'originale resta
     nell'audit con tutte le righe.
Prima di scrivere qualsiasi cosa controlla che l'annullo sia possibile; l'ordine nuovo si crea solo dopo. Se l'annullo
fallisse dopo la creazione, lo script lo dice e stampa il comando per annullare il nuovo (nulla va perso).

Rifiuta (nulla scritto): ordine non APERTO o con qualsiasi consegna; riga non individuata (nome varieta' o RO-...); ordine
a una sola riga (per toglierla tutta si annulla l'ordine); stralcio di tutte le righe; allocazioni RACCOLTA su raccolte non
caricate a stock.

ATTENZIONE: il nuovo ordine e' MANUALE, non legato al programma di fornitura. L'ordine vecchio resta annullato col suo
codice di idempotenza, quindi lo scheduler non lo rigenera; `2026-10-15_controllo_programmi.py` segnalera' pero' MANCA per
quella data: e' voluto. Il programma NON viene modificato (per cambiarlo: 2026-10-14_quantita_programma.py).

Sempre in ANTEPRIMA finche' non aggiungi --esegui.
Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-16_stralcia_riga.py ORD-000055 Rabano --motivo "il cliente non vuole il Rabano"
  ... --esegui    per scrivere davvero            (--riga ripetibile: piu' righe da togliere: ORD-000055 Rabano Mizuna)
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

from src.tpo_core.infrastructure.postgresql.order_amendment import (  # noqa: E402
    OrderAmendmentError, find_line, read_order,
)
from src.tpo_core.infrastructure.postgresql.order_cancellation import (  # noqa: E402
    OrderCancellationError, cancel, preview, unsafe_harvest_allocations,
)

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
ACTOR = "matteo"
PROVENANCE = "commissioning:2026-10-16_stralcia_riga"
SELF = "scripts/commissioning/2026-10-16_stralcia_riga.py"
MODIFICA = "scripts/commissioning/2026-10-07_modifica_ordine.py"


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def _dettagli(cur, order):
    cur.execute("""SELECT cl.public_id, cl.denominazione, o.data_ordine, o.data_consegna_prevista
                   FROM tpo.ordini o JOIN tpo.clienti cl ON cl.id=o.cliente_id WHERE o.id=%s""", (order.pk,))
    cli_pid, cli_nome, data_ordine, data_consegna = cur.fetchone()
    cur.execute("""SELECT ro.public_id, v.public_id FROM tpo.righe_ordine ro JOIN tpo.varieta v ON v.id=ro.varieta_id
                   WHERE ro.ordine_id=%s""", (order.pk,))
    varieta_pid = {ro: v for ro, v in cur.fetchall()}
    return cli_pid, cli_nome, data_ordine, data_consegna, varieta_pid


def run(conn, ordine: str, selettori: list[str], motivo: str, esegui: bool, out=print,
        runner=lambda cmd: subprocess.run(cmd, capture_output=True, text=True)) -> int:
    cur = conn.cursor()
    try:
        order = read_order(cur, ordine)
        if order.state != "APERTO":
            raise OrderAmendmentError(f"{ordine}: stato {order.state} (si stralcia solo un ordine APERTO).")
        if order.delivery_rows:
            raise OrderAmendmentError(f"{ordine}: ha consegne registrate; per il residuo non dovuto usa la chiusura del residuo.")
        if len(order.lines) < 2:
            raise OrderAmendmentError(f"{ordine} ha una sola riga: per toglierla si annulla l'ordine "
                                      f"(modifica_ordine.py annulla {ordine}).")
        togliere = []
        for sel in selettori:
            riga = find_line(order, sel)
            if riga not in togliere:
                togliere.append(riga)
        restano = [r for r in order.lines if r not in togliere]
        if not restano:
            raise OrderAmendmentError("stralcio di TUTTE le righe: per togliere tutto si annulla l'ordine.")
        if any(r.public_id is None for r in order.lines):
            raise OrderAmendmentError(f"{ordine}: una riga senza identificativo RO-.")
        cli_pid, cli_nome, data_ordine, data_consegna, varieta_pid = _dettagli(cur, order)
        if data_consegna is None:
            raise OrderAmendmentError(f"{ordine} non ha la data di consegna prevista.")
        before = data_consegna + timedelta(days=1)
        _, allocazioni = preview(cur, (ordine,), before)
        if unsafe_harvest_allocations(allocazioni):
            raise OrderCancellationError("allocazioni RACCOLTA su raccolte non interamente caricate a stock: serve una decisione.")
    except (OrderAmendmentError, OrderCancellationError) as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2

    out(f"== STRALCIO RIGHE {ordine} - {cli_nome} ({'ESECUZIONE' if esegui else 'ANTEPRIMA, NULLA VIENE SCRITTO'})")
    out(f"Ordine {ordine}: consegna prevista {data_consegna}, d'ordine {data_ordine}, programma {order.program or '-'}, "
        f"{order.creation_type}")
    for r in order.lines:
        marca = "   <-- TOLTA" if r in togliere else ""
        out(f"   {r.public_id}  {r.variety} {_n(r.quantity)} {r.unit}{marca}")
    out(f"\nVerra' creato un NUOVO ordine manuale (stesso cliente e date) con: "
        + ", ".join(f"{r.variety} {_n(r.quantity)}" for r in restano))
    out(f"Poi {ordine} viene ANNULLATO ({len(allocazioni)} allocazioni attive RILASCIATE; l'originale resta nell'audit).")
    if order.program:
        out(f"Il nuovo ordine NON e' legato a {order.program}; il programma non cambia (il controllo programmi segnalera' MANCA "
            "per questa data: e' voluto).")
    out(f"Motivo registrato: {motivo}")
    if not esegui:
        conn.rollback()
        out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        return 0

    chiave = "stralcio-" + ordine + "-" + hashlib.sha256(",".join(sorted(r.public_id for r in togliere)).encode()).hexdigest()[:10]
    righe_cli = []
    for r in restano:
        righe_cli += ["--riga", f"{varieta_pid[r.public_id]}:{_n(r.quantity)}:{r.unit}"]
    reason_nuovo = f"Stralcio di {', '.join(r.variety for r in togliere)} dall'ordine {ordine}: {motivo}"
    cmd = [RUN, "ordine", "registra-manuale", "--client", cli_pid, "--data-ordine", data_ordine.isoformat(),
           "--data-consegna-prevista", data_consegna.isoformat(), *righe_cli, "--actor", ACTOR, "--reason", reason_nuovo,
           "--correlation-id", chiave, "--idempotency-key", chiave, "--confirm"]
    done = runner(cmd)
    testo = (done.stdout or "") + (done.stderr or "")
    nuovo = re.search(r"ORDINE_ID:\s*(ORD-\d+)", testo)
    if done.returncode != 0 or not nuovo:
        conn.rollback()
        out(f"ERRORE, il nuovo ordine NON e' stato creato e {ordine} non e' stato toccato:\n{testo.rstrip()}")
        return 4
    nuovo_id = nuovo.group(1)
    out(f"\nCreato il nuovo ordine {nuovo_id}.")
    reason_annullo = (f"Stralcio di {', '.join(r.variety for r in togliere)} dichiarato da Matteo: ordine sostituito da "
                      f"{nuovo_id} con le righe rimaste. {motivo}")
    try:
        cancel(cur, order_public_ids=(ordine,), before=before, actor=ACTOR, reason=reason_annullo,
               correlation_id=chiave, provenance=PROVENANCE)
        conn.commit()
    except Exception as exc:  # il nuovo esiste, il vecchio no annullato: dillo e dai il correttivo
        conn.rollback()
        out(f"ERRORE nell'annullo di {ordine}: {exc}\n{nuovo_id} ESISTE gia' e {ordine} e' ancora APERTO: ora la domanda e' "
            f"doppia. Per annullare il nuovo:\n   .venv/bin/python {MODIFICA} annulla {nuovo_id} "
            f"--motivo \"Stralcio non completato\" --esegui")
        return 5
    out(f"FATTO: {ordine} ANNULLATO, sostituito da {nuovo_id}.")
    out("\n== COMANDO CORRETTIVO (rimettere la riga = annullare il nuovo e ricreare l'ordine originale):")
    out(f"   .venv/bin/python {MODIFICA} annulla {nuovo_id} --motivo \"Stralcio da rimettere\" --esegui")
    out("   poi registra un ordine manuale con le righe originali: "
        + ", ".join(f"{r.variety} {_n(r.quantity)}" for r in order.lines))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ordine", help="es. ORD-000055")
    ap.add_argument("righe", nargs="+", help="riga/e da togliere: nome varieta' o RO-...")
    ap.add_argument("--motivo", required=True)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, a.ordine, a.righe, a.motivo, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
