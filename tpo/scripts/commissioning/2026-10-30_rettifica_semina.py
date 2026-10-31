"""Rettifica governata dei SET attesi e/o della finestra di raccolta di una SEMINA gia' compilata (30/10/2026).

Serve quando il sistema e' DISTACCATO dalla realta' (es. SEM-000043: 4 raccolte registrate sopra l'Afila che
fisicamente veniva da SEM-000030; a sistema restano 3 SET, in realta' ce ne sono 8). Le raccolte e le consegne
gia' fatte NON si toccano (autorita' immutabili); si rettifica solo la previsione della semina:
  set=N        SET attesi TOTALI della semina (intero >= 1, >= dei SET gia' raccolti); la quantita' attesa
               diventa N x resa del protocollo (la resa del protocollo deve essere in SET)
  inizio=DATA  nuovo inizio finestra di raccolta (AAAA-MM-GG, l'ora resta quella attuale)
  fine=DATA    nuova fine finestra di raccolta (AAAA-MM-GG, l'ora resta quella attuale)
Non cambia stato, seme, lotto, protocollo, raccolte, stock, ordini, piani. Per ogni semina: UPDATE con controllo
di versione (+1) e audit SEMINA/UPDATE con before/after e motivo. Una sola transazione (o niente).

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-30_rettifica_semina.py \\
      --semina SEM-000043:set=11 --motivo "testo" [--semina SEM-000044:inizio=2026-10-27] [--esegui]
Senza --esegui e' solo ANTEPRIMA (non scrive nulla).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

ACTOR = "matteo"
TAG = "rettifica-semina-2026-10-30"
SEM = re.compile(r"^SEM-\d{6,}$")


class Stop(Exception):
    pass


def parse_spec(text: str) -> tuple[str, dict]:
    sem, _, rest = text.partition(":")
    if not SEM.match(sem) or not rest:
        raise Stop(f"--semina {text!r}: usa SEM-000000:set=N[,inizio=AAAA-MM-GG][,fine=AAAA-MM-GG].")
    values: dict = {}
    for part in rest.split(","):
        key, _, value = part.partition("=")
        if key == "set":
            if not value.isdigit() or int(value) < 1:
                raise Stop(f"{sem}: set={value!r} deve essere un intero >= 1.")
            values["set"] = int(value)
        elif key in ("inizio", "fine"):
            try:
                values[key] = date.fromisoformat(value)
            except ValueError:
                raise Stop(f"{sem}: {key}={value!r} deve essere AAAA-MM-GG.") from None
        else:
            raise Stop(f"{sem}: chiave sconosciuta {key!r} (ammesse: set, inizio, fine).")
    return sem, values


def _with_date(existing: datetime, day: date) -> datetime:
    return datetime.combine(day, existing.timetz())


def piano(cur, specs: dict[str, dict]):
    from src.tpo_core.infrastructure.postgresql import semina_predictive_authority as authority
    found = {item.public_id: item for item in authority.read(cur, tuple(sorted(specs)), lock=True)}
    missing = sorted(set(specs) - set(found))
    if missing:
        raise Stop(f"Semine inesistenti, chiuse o non in GRAMMI: {', '.join(missing)}")
    out = []
    for sem in sorted(specs):
        item, want = found[sem], specs[sem]
        if not item.is_filled:
            raise Stop(f"{sem}: non ancora compilata (usa 2026-10-06_compila_semine_in_corso.py --set {sem}=N).")
        quantity, uom, start, end = item.filled
        new_q, new_start, new_end = quantity, start, end
        if "set" in want:
            if item.yield_uom != "SET" or uom != "SET":
                raise Stop(f"{sem}: la resa del protocollo non e' in SET ({item.yield_uom}/{uom}).")
            if Decimal(want["set"]) < item.harvested_sets:
                raise Stop(f"{sem}: gia' raccolti {item.harvested_sets} SET, piu' dei {want['set']} indicati.")
            new_q = Decimal(want["set"]) * item.expected_yield
        if "inizio" in want:
            new_start = _with_date(start, want["inizio"])
        if "fine" in want:
            new_end = _with_date(end, want["fine"])
        if new_end <= new_start:
            raise Stop(f"{sem}: la fine finestra ({new_end:%Y-%m-%d}) deve essere dopo l'inizio ({new_start:%Y-%m-%d}).")
        out.append((item, (quantity, start, end), (new_q, new_start, new_end)))
    return out


def run(conn, specs: dict[str, dict], motivo: str, esegui: bool, out=print) -> int:
    from psycopg.types.json import Jsonb
    cur = conn.cursor()
    try:
        righe = piano(cur, specs)
        out("semina | varieta | stato | raccolti | SET attesi (prima -> dopo) | finestra (prima -> dopo)")
        da_scrivere = []
        for item, before, after in righe:
            cambia = before != after
            out(f"{item.public_id} | {item.variety} | {item.state} | {item.harvested_sets} | "
                f"{before[0]} -> {after[0]} | {before[1]:%Y-%m-%d} / {before[2]:%Y-%m-%d} -> "
                f"{after[1]:%Y-%m-%d} / {after[2]:%Y-%m-%d}" + ("" if cambia else "  (gia' cosi', niente da fare)"))
            if cambia:
                da_scrivere.append((item, before, after))
        if not da_scrivere:
            out("\nNiente da scrivere.")
            conn.rollback()
            return 0
        if not esegui:
            out("\nANTEPRIMA: nulla scritto. Se la tabella e' giusta, rilancia con --esegui.")
            conn.rollback()
            return 0
        for item, before, after in da_scrivere:
            cur.execute(
                """UPDATE tpo.semine SET expected_useful_quantity=%s, harvest_window_start=%s,
                          harvest_window_end=%s, version=version+1
                   WHERE id=%s AND version=%s AND stato<>'CHIUSA' RETURNING version""",
                (after[0], after[1], after[2], item.pk, item.version))
            if cur.fetchone() != (item.version + 1,):
                raise Stop(f"{item.public_id}: la semina e' cambiata nel frattempo (versione), riprova.")
            cur.execute(
                """INSERT INTO tpo.audit_eventi
                     (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                      before_data,after_data,correlation_id,provenance)
                   VALUES (CURRENT_TIMESTAMP,%s,'SEMINA',%s,'UPDATE',%s,%s,%s,%s,%s)""",
                (ACTOR, item.public_id, motivo,
                 Jsonb({"expected_useful_quantity": str(before[0]), "harvest_window_start": before[1].isoformat(),
                        "harvest_window_end": before[2].isoformat(), "version": item.version}),
                 Jsonb({"expected_useful_quantity": str(after[0]), "harvest_window_start": after[1].isoformat(),
                        "harvest_window_end": after[2].isoformat(), "version": item.version + 1,
                        "harvested_sets": str(item.harvested_sets)}),
                 f"{TAG}-{item.public_id}", Jsonb({"rettifica_previsione": "OWNER_AUTHORIZED"})))
        conn.commit()
        out(f"\nFATTO. Rettificate {len(da_scrivere)} semine: {', '.join(i.public_id for i, _, _ in da_scrivere)}.")
        out("Per il fabbisogno aggiornato: .venv/bin/python scripts/commissioning/2026-10-06_piano_ipotetico.py")
        return 0
    except Stop:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--semina", action="append", required=True, metavar="SEM-000000:set=N[,inizio=D][,fine=D]")
    ap.add_argument("--motivo", required=True)
    ap.add_argument("--esegui", action="store_true")
    a = ap.parse_args()
    try:
        specs: dict[str, dict] = {}
        for text in a.semina:
            sem, values = parse_spec(text)
            if sem in specs:
                raise Stop(f"{sem} indicata due volte.")
            specs[sem] = values
        if not a.motivo.strip():
            raise Stop("--motivo obbligatorio.")
        from secret_boundary import load_postgresql_parameters
        import psycopg
        p = load_postgresql_parameters()
        conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                               password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
        try:
            return run(conn, specs, a.motivo, a.esegui)
        finally:
            conn.close()
    except Stop as exc:
        print(f"\nSTOP: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
