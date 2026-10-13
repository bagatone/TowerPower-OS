"""Crea un NUOVO programma di fornitura ricorrente per un cliente (8/10/2026, richiesta di Matteo: Salvaje).

Sempre in ANTEPRIMA finche' non aggiungi --esegui. Usa `tpo onboarding supply-program` (versione 1, ATTIVO). Le righe
sono OGNI_X_GIORNI: la prima consegna e' --prima-consegna, poi una ogni --ogni-giorni giorni. Il giorno della
settimana segue dalla data scelta. Orario di generazione e finestra operativa come gli altri programmi (05:00 e 14
giorni, modificabili). Non crea ordini: li genera lo scheduler.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-08_nuovo_programma.py Salvaje --prima-consegna 2026-10-20 \\
      --riga Afila:2 --riga Cilantro:1 --ogni-giorni 14 --motivo "Salvaje ricorrente: ogni 2 settimane 2 Afila + 1 Cilantro"
  ... --esegui    per scrivere davvero

Rifiuta: cliente inesistente o con un programma ATTIVO corrente (ne puo' avere uno solo), varieta' sconosciute o
ripetute, quantita' <= 0, prima consegna nel passato.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
ACTOR = "matteo"
TIMEZONE = ZoneInfo("Atlantic/Canary")
GIORNI = ["lunedi'", "martedi'", "mercoledi'", "giovedi'", "venerdi'", "sabato", "domenica"]


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").strip()


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


class Refused(Exception):
    pass


def prepare(cur, cliente: str, righe: list[str], prima: date, today: date):
    cur.execute("SELECT id, public_id, denominazione FROM tpo.clienti")
    clients = [r for r in cur.fetchall() if _fold(r[2]) == _fold(cliente)]
    if len(clients) != 1:
        raise Refused(f"cliente '{cliente}': trovati {len(clients)} (atteso 1).")
    cid, cpublic, cname = clients[0]
    cur.execute("""SELECT pf.public_id FROM tpo.programmi_fornitura pf
                   JOIN tpo.programmi_fornitura_versioni v ON v.programma_fornitura_id=pf.id
                   WHERE pf.cliente_id=%s AND v.valida_al IS NULL AND v.stato='ATTIVO'""", (cid,))
    active = cur.fetchall()
    if active:
        raise Refused(f"{cname} ha gia' un programma ATTIVO ({active[0][0]}): se ne puo' avere uno solo. "
                      "Per cambiarlo serve una nuova versione, non un nuovo programma.")
    if prima < today:
        raise Refused(f"prima consegna {prima} nel passato (oggi {today}).")
    cur.execute("SELECT public_id, denominazione FROM tpo.varieta")
    varieties = {_fold(name): (pid, name) for pid, name in cur.fetchall()}
    lines, seen = [], set()
    for item in righe:
        name, _, qty = item.partition(":")
        if _fold(name) not in varieties:
            raise Refused(f"varieta' sconosciuta: {name}")
        try:
            quantity = Decimal(qty.replace(",", "."))
        except InvalidOperation:
            raise Refused(f"quantita' non valida in '{item}' (formato Varieta:SET)")
        if quantity <= 0:
            raise Refused(f"quantita' <= 0 in '{item}'")
        pid, vname = varieties[_fold(name)]
        if pid in seen:
            raise Refused(f"varieta' ripetuta: {vname}")
        seen.add(pid)
        lines.append((pid, vname, quantity))
    if not lines:
        raise Refused("indica almeno una --riga Varieta:SET.")
    cur.execute("SELECT public_id FROM tpo.programmi_fornitura WHERE public_id ~ '^PF-[0-9]{6,}$'")
    numbers = [int(re.match(r"^PF-(\d+)$", r[0]).group(1)) for r in cur.fetchall()]
    program_id = f"PF-{(max(numbers) if numbers else 0) + 1:06d}"
    return cpublic, cname, program_id, lines


def run(conn, cliente: str, righe: list[str], prima: date, ogni: int, motivo: str, esegui: bool,
        generazione: str = "05:00", finestra: int = 14, today: date | None = None, out=print, runner=None) -> int:
    today = today or datetime.now(TIMEZONE).date()
    cur = conn.cursor()
    try:
        cpublic, cname, program_id, lines = prepare(cur, cliente, righe, prima, today)
    except Refused as exc:
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    if ogni <= 0:
        out("RIFIUTATO, nulla scritto: --ogni-giorni deve essere > 0.")
        return 2
    out(f"== NUOVO PROGRAMMA DI FORNITURA ({'ESECUZIONE' if esegui else 'ANTEPRIMA, NULLA VIENE SCRITTO'})")
    out(f"{program_id} per {cname} ({cpublic}): versione 1, ATTIVO, dal {prima} ({GIORNI[prima.weekday()]})")
    out(f"Una consegna ogni {ogni} giorni a partire dal {prima}; generazione ordini ore {generazione}, "
        f"finestra operativa {finestra} giorni.")
    for _, vname, quantity in lines:
        out(f"  riga: {vname} {_n(quantity)} SET")
    out("Prime consegne: " + ", ".join(
        f"{date.fromordinal(prima.toordinal() + ogni * k)}" for k in range(4)))
    out(f"Motivo registrato: {motivo}")
    if not esegui:
        out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        return 0
    args = [RUN, "onboarding", "supply-program", "--program-id", program_id, "--customer-id", cpublic,
            "--version", "1", "--state", "ATTIVO", "--start-date", prima.isoformat(),
            "--generation-time", generazione, "--operational-window-days", str(finestra),
            "--valid-from", datetime.now(TIMEZONE).replace(microsecond=0).isoformat()]
    for pid, _, quantity in lines:
        args += ["--line", f"{pid},{_n(quantity)},SET,OGNI_X_GIORNI,{ogni},"]
    args += ["--actor", ACTOR, "--reason", motivo,
             "--correlation-id", f"nuovo-programma-{cpublic}-{program_id}"]
    runner = runner or (lambda a: subprocess.run(a, capture_output=True, text=True))
    done = runner(args)
    out((done.stdout or "").rstrip())
    if done.returncode != 0:
        out(((done.stderr or "").rstrip()) + f"\nERRORE (exit {done.returncode}): nulla scritto o da verificare.")
        return 1
    out(f"\nFATTO: {program_id} creato. Controlla con: .venv/bin/python "
        f"scripts/commissioning/2026-10-07_programma_fornitura.py {program_id}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cliente")
    ap.add_argument("--prima-consegna", required=True, help="AAAA-MM-GG")
    ap.add_argument("--riga", action="append", default=[], help="Varieta:SET (ripetibile)")
    ap.add_argument("--ogni-giorni", type=int, default=14)
    ap.add_argument("--generazione", default="05:00")
    ap.add_argument("--finestra-giorni", type=int, default=14)
    ap.add_argument("--motivo", required=True)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, a.cliente, a.riga, date.fromisoformat(a.prima_consegna), a.ogni_giorni, a.motivo,
                   a.esegui, a.generazione, a.finestra_giorni)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
