"""Raccolte storiche vendute fuori sistema: carico a magazzino + rettifica "vendita non registrata".

Decisione di Matteo (5/10/2026): RAC-000001 (Afila 1 SET), RAC-000002 (Cilantro 1 SET),
RAC-000003 (Afila 2 SET) e RAC-000004 (Cilantro 1 SET) sono state vendute, ma le consegne non sono mai state registrate.
Finche' queste raccolte non sono ne' caricate a magazzino ne' scaricate, il planner le
rivede come merce libera. Stesso schema del 3/10 (fasi 3-4 dell'avvio pulito):

  1. `movimento carica-raccolta`   -> la raccolta entra a magazzino (istante = data della raccolta)
  2. `movimento rettifica-giacenza` -> uscita "vendita non registrata", stessa quantita',
                                       con la semina d'origine (tracciabilita' preservata)

Effetto netto sullo stock: zero. Nessun cliente, nessuna consegna, nessuna fattura inventata:
la rettifica dice la verita' (venduta, a chi e quando non e' noto).

Uso (dalla cartella del progetto):
    .venv/bin/python scripts/commissioning/2026-10-05_scarica_raccolte_storiche.py            # anteprima
    .venv/bin/python scripts/commissioning/2026-10-05_scarica_raccolte_storiche.py --esegui   # scrive

Rilanciabile: salta cio' che e' gia' stato fatto (idempotency-key fisse) e si ferma se lo
stato del database non e' quello dichiarato (raccolta diversa, gia' caricata a meta', ecc.).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
ACTOR = "matteo"
TAG = "scarica-raccolte-storiche-2026-10-05"
# Data di registrazione della vendita: la data reale non e' nota (dichiarato da Matteo).
RETTIFICA_AT = "2026-10-05T00:00:00+01:00"

# raccolta -> (varieta, quantita SET attesa): se il database dice altro, ci si ferma.
ATTESE = {
    "RAC-000001": ("Afila", Decimal("1")),
    "RAC-000002": ("Cilantro", Decimal("1")),
    "RAC-000003": ("Afila", Decimal("2")),
    "RAC-000004": ("Cilantro", Decimal("1")),
}


class Stop(Exception):
    pass


@dataclass(frozen=True)
class Raccolta:
    public_id: str
    variety_id: str
    variety_name: str
    semina: str
    harvested_at: object  # datetime
    quantity: Decimal
    unit: str
    loaded: Decimal


def _find(cursor, ids) -> dict[str, Raccolta]:
    cursor.execute(
        """SELECT rc.public_id, v.public_id, v.denominazione, s.public_id, rc.data_raccolta,
                  rc.quantita, rc.unita_misura::text,
                  COALESCE((SELECT SUM(m.quantita) FROM tpo.movimenti_magazzino m
                            WHERE m.raccolta_id=rc.id AND m.tipo='CARICO'
                              AND m.unita_misura=rc.unita_misura),0)
           FROM tpo.raccolte rc JOIN tpo.semine s ON s.id=rc.semina_id
           JOIN tpo.varieta v ON v.id=s.varieta_id
           WHERE rc.public_id = ANY(%s)""", (list(ids),))
    return {r[0]: Raccolta(r[0], r[1], r[2], r[3], r[4], Decimal(r[5]), r[6], Decimal(r[7]))
            for r in cursor.fetchall()}


def _done(cursor, scope: str, key: str) -> bool:
    cursor.execute("SELECT 1 FROM tpo.movimento_carico_requests "
                   "WHERE operation_scope=%s AND idempotency_key=%s", (scope, key))
    return cursor.fetchone() is not None


def _validate(found: dict[str, Raccolta], cursor) -> None:
    for rac, (nome, qty) in ATTESE.items():
        item = found.get(rac)
        if item is None:
            raise Stop(f"{rac} non esiste.")
        if item.variety_name != nome or item.unit != "SET" or item.quantity != qty:
            raise Stop(f"{rac}: nel database e' {item.variety_name} {item.quantity} {item.unit}, "
                       f"dichiarato {nome} {qty} SET. Non procedo alla cieca.")
        carico_done = _done(cursor, "MOVIMENTO_CARICO_RACCOLTA_V1", f"{TAG}-carico-{rac}")
        if item.loaded not in (Decimal("0"), qty) or (item.loaded == qty and not carico_done):
            raise Stop(f"{rac}: caricato a magazzino {item.loaded} SET (su {qty}) da un'operazione "
                       "non di questo script. Dimmi cosa e' successo prima di toccare altro.")


def commands(item: Raccolta) -> list[tuple[str, list[str], str, str]]:
    """(scope, argomenti tpo, chiave idempotency, etichetta) per una raccolta."""
    qty = f"{item.quantity.normalize():f}"
    when = item.harvested_at.isoformat()
    carico_motivo = (f"Carico a magazzino della raccolta storica {item.public_id} "
                     f"{item.variety_name} {qty} SET ({item.semina}), mai caricata prima")
    vendita_motivo = (f"Vendita non registrata: {item.variety_name} {qty} SET della raccolta "
                      f"{item.public_id} ({item.semina}), venduti fuori sistema; cliente e data non noti, "
                      "dichiarato da Matteo il 5/10/2026")
    k_car, k_ven = f"{TAG}-carico-{item.public_id}", f"{TAG}-venduto-{item.public_id}"
    return [
        ("MOVIMENTO_CARICO_RACCOLTA_V1",
         ["movimento", "carica-raccolta", "--raccolta", item.public_id, "--unita-misura", "SET",
          "--effective-at", when, "--motivo", carico_motivo, "--actor", ACTOR, "--reason", carico_motivo,
          "--correlation-id", k_car, "--idempotency-key", k_car, "--confirm"],
         k_car, f"carico {item.public_id} ({item.variety_name} {qty} SET)"),
        ("MOVIMENTO_RETTIFICA_GIACENZA_V1",
         ["movimento", "rettifica-giacenza", "--varieta", item.variety_id, "--unita-misura", "SET",
          "--quantita", qty, "--semina", item.semina, "--effective-at", RETTIFICA_AT,
          "--motivo", vendita_motivo, "--actor", ACTOR, "--reason", vendita_motivo,
          "--correlation-id", k_ven, "--idempotency-key", k_ven, "--confirm"],
         k_ven, f"rettifica {item.public_id}: -{qty} SET {item.variety_name} (vendita non registrata)"),
    ]


def run(conn, esegui: bool, out=print) -> int:
    cur = conn.cursor()
    found = _find(cur, tuple(ATTESE))
    try:
        _validate(found, cur)
    except Stop as exc:
        out(f"STOP: {exc}")
        return 3
    cur.execute("SELECT v.denominazione, s.disponibile FROM tpo.stock s JOIN tpo.varieta v ON v.id=s.varieta_id "
                "WHERE s.unita_misura='SET' AND v.denominazione = ANY(%s) ORDER BY 1",
                (sorted({n for n, _ in ATTESE.values()}),))
    stock = {r[0]: r[1] for r in cur.fetchall()}
    out("Stock SET attuale: " + (", ".join(f"{k} {v}" for k, v in stock.items()) or "nessuno"))
    for rac in ATTESE:
        item = found[rac]
        out(f"{rac}: {item.variety_name} {item.quantity} SET, semina {item.semina}, "
            f"raccolta del {item.harvested_at:%Y-%m-%d %H:%M}, caricato a magazzino finora: {item.loaded}")
    for rac in ATTESE:
        for scope, args, key, label in commands(found[rac]):
            if _done(cur, scope, key):
                out(f"\n--- {label}: gia' eseguito, salto.")
                continue
            shown = " ".join(a if re.fullmatch(r"[\w./:+=,-]+", a) else repr(a) for a in args)
            out(f"\n--- {label}\n$ tpo {shown}")
            if not esegui:
                out("   (anteprima: non eseguito)")
                continue
            done = subprocess.run([RUN, *args], capture_output=True, text=True)
            out(((done.stdout or "") + (done.stderr or "")).rstrip())
            if done.returncode != 0:
                out(f"STOP: comando fallito (exit {done.returncode}): {label}")
                return 4
    out("\nFATTO." if esegui else
        "\nANTEPRIMA: nulla scritto. Effetto netto sullo stock: zero. Per eseguire: aggiungi --esegui.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--esegui", action="store_true", help="scrive davvero (senza: anteprima)")
    args = parser.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"],
                           connect_timeout=p["connect_timeout"], autocommit=True)
    try:
        return run(conn, args.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
