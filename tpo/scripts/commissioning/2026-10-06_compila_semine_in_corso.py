"""Rende visibili al planner le semine fisiche in corso (resa attesa + finestra di raccolta), dal protocollo.

Regole (decise da Matteo il 6/10/2026):
  - un SET resta sempre un SET: il numero di SET di ogni semina e' un INTERO dichiarato, mai calcolato dai grammi
    (un SET sperimentale con meno seme e' comunque 1 SET). Lo script PROPONE l'intero solo dove i grammi
    corrispondono esattamente a N SET del protocollo; per le altre semine devi dichiararlo con --set SEM-...=N;
  - resa attesa = SET x resa del protocollo (1 SET per SET); finestra = avvio + germinazione + luce + buffer,
    lunga 5 giorni (--giorni-finestra);
  - le semine gia' compilate non si toccano; chiuse non compaiono.

Senza --esegui NON scrive nulla (anteprima). Con --esegui scrive TUTTO in una sola transazione (o niente) e
solo se ogni semina in anteprima e' DA_COMPILARE o GIA_COMPILATA (o esclusa con --escludi).

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-06_compila_semine_in_corso.py
  .venv/bin/python scripts/commissioning/2026-10-06_compila_semine_in_corso.py --set SEM-000018=1 --set SEM-000005=2
  ... --escludi SEM-000010            # semine da non compilare (es. stato fisico da verificare)
  ... --esegui                        # scrive
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

from src.tpo_core.application.production_planning.in_progress_authority import DEFAULT_WINDOW_DAYS  # noqa: E402
from src.tpo_core.infrastructure.postgresql import semina_predictive_authority as authority  # noqa: E402

ACTOR = "matteo"
PROVENANCE = json.dumps({"declared_sets": "OWNER_AUTHORIZED", "harvest_window_days": "OWNER_AUTHORIZED",
                         "derivation": "PROTOCOL_VERSION"}, sort_keys=True)
TAG = "predittivo-2026-10-06"


def parse_sets(values) -> dict[str, int]:
    declared: dict[str, int] = {}
    for item in values or ():
        key, _, value = item.partition("=")
        if not key.startswith("SEM-") or not value.isdigit() or int(value) < 1:
            raise SystemExit(f"STOP: --set {item!r}: usa SEM-000000=N con N intero >= 1.")
        declared[key] = int(value)
    return declared


def report(rows, now, out=print) -> dict[str, int]:
    out("semina | varieta | stato | avvio | seme g | SET | gia' raccolti | resa | finestra raccolta | esito")
    to_write: dict[str, int] = {}
    for item, sets, derived, state in rows:
        window = (f"{derived.window_start:%Y-%m-%d} -> {derived.window_end:%Y-%m-%d}" if derived else
                  (f"{item.filled[2]:%Y-%m-%d} -> {item.filled[3]:%Y-%m-%d}" if item.is_filled else "-"))
        notes = []
        if derived and derived.window_end < now:
            notes.append("FINESTRA GIA' CONCLUSA: la semina e' ancora in stato "
                         f"{item.state}, verifica se esiste ancora fisicamente")
        if state == "SERVE_SET":
            notes.append(f"i grammi ({item.seed_grams} g su {item.grams_per_set} g/SET) non corrispondono a SET interi: "
                         f"dichiara --set {item.public_id}=N")
        if state == "INCOERENTE_RACCOLTO_OLTRE_SET":
            notes.append(f"raccolti {item.harvested_sets} SET, piu' dei {sets} indicati")
        out(f"{item.public_id} | {item.variety} | {item.state} | {item.started_at:%Y-%m-%d} | {item.seed_grams} | "
            f"{sets if sets is not None else '?'} | {item.harvested_sets} | "
            f"{(str(derived.quantity) + ' ' + derived.uom) if derived else '-'} | {window} | {state}"
            + ("  <<< " + "; ".join(notes) if notes else ""))
        if state == "DA_COMPILARE":
            to_write[item.public_id] = sets
    return to_write


def run(conn, declared, exclude, esegui, window_days=DEFAULT_WINDOW_DAYS, now=None, out=print) -> int:
    now = now or datetime.now().astimezone()
    cur = conn.cursor()
    rows = authority.plan(cur, declared, exclude=tuple(exclude), window_days=window_days)
    unknown = sorted(set(declared) - {row[0].public_id for row in rows})
    if unknown:
        out(f"STOP: semine indicate con --set non trovate o gia' chiuse: {', '.join(unknown)}")
        return 3
    to_write = report(rows, now, out)
    blocked = [row[0].public_id for row in rows if row[3] in ("SERVE_SET", "INCOERENTE_RACCOLTO_OLTRE_SET", "NON_DERIVABILE")]
    out(f"\nDa compilare: {len(to_write)}; gia' compilate: {sum(1 for r in rows if r[3] == 'GIA_COMPILATA')}; "
        f"bloccate: {len(blocked)}")
    if blocked:
        out(f"STOP: risolvi prima le semine bloccate ({', '.join(blocked)}) con --set SEM-...=N o --escludi.")
        return 2
    if not to_write:
        out("Niente da scrivere.")
        return 0
    if not esegui:
        out("\nANTEPRIMA: nulla scritto. Se la tabella e' giusta, rilancia con --esegui.")
        return 0
    reason = (f"Compilazione resa attesa e finestra di raccolta ({window_days} giorni) di {len(to_write)} semine in "
              "corso, dal protocollo, con SET dichiarati da Matteo il 6/10/2026, perche' il planner veda la "
              "produzione fisica.")
    try:
        done, replays = authority.commission_predictive(
            cur, declared_sets=to_write, actor=ACTOR, reason=reason, correlation_id=TAG,
            provenance=PROVENANCE, window_days=window_days)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    out(f"\nFATTO. Compilate {len(done)} semine: {', '.join(done)}.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true")
    ap.add_argument("--set", action="append", metavar="SEM-000000=N", help="SET dichiarati per una semina")
    ap.add_argument("--escludi", default="", help="semine da non compilare, separate da virgola")
    ap.add_argument("--giorni-finestra", type=int, default=DEFAULT_WINDOW_DAYS)
    args = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, parse_sets(args.set), [x for x in args.escludi.split(",") if x],
                   args.esegui, args.giorni_finestra)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
