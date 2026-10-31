"""FATTURE DEL MESE (31/10/2026): anteprima e, cliente per cliente, emissione delle fatture di un mese.

  .venv/bin/python scripts/commissioning/2026-10-31_fatture_mese.py                       # anteprima ottobre, tutti i clienti
  .venv/bin/python scripts/commissioning/2026-10-31_fatture_mese.py --mese 2026-10 --cliente Bahia
  .venv/bin/python scripts/commissioning/2026-10-31_fatture_mese.py --cliente Bahia --data-emissione 2026-10-31 --esegui

Per ogni cliente mostra le consegne CONSEGNATE del mese non ancora fatturate, il listino, i totali (netto, IGIC, totale),
la modalita' di fatturazione e i termini di pagamento configurati, e se la fattura e' EMETTIBILE o cosa manca.
I clienti che non vogliono fattura (es. Alchimia, Oca Bianca) si escludono con --senza-fattura "Alchimia,Oca Bianca"
(per nome, anche una parte): vengono solo elencati come "senza fattura", non toccati.

Regole del sistema (docs/architecture/FATTURA_AUTHORITY_FREEZE.md): A_CONSEGNA = una fattura per consegna;
PERIODICA_MENSILE = una fattura con tutte le consegne del mese. Una riga fattura per riga di consegna. Numerazione
AAAA/NNNN senza buchi, assegnata dal sistema: per questo l'emissione si fa SOLO con --cliente (un cliente alla volta,
dopo aver visto l'anteprima) e SOLO con --esegui. Una fattura emessa e' definitiva: si corregge solo con `fattura rettifica`.
Se manca la configurazione del cliente il comando per impostarla viene stampato (la scelta e' tua: non la invento).
Rilanciare lo stesso comando non crea una seconda fattura (chiave di idempotenza dalle consegne).
Il sistema NON produce PDF/documento stampabile della fattura e non conserva dati fiscali del cliente (solo denominazione).
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

TIMEZONE = ZoneInfo("Atlantic/Canary")
RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
RUN_REL = "scripts/commissioning/run_tpo.sh"
ACTOR = "matteo"
CENT = Decimal("0.01")

SQL_CONSEGNE = """
SELECT c.id, c.public_id, cl.id, cl.public_id, cl.denominazione, c.data_effettiva,
       cl.modalita_fatturazione, cl.termini_pagamento_giorni,
       EXISTS (SELECT 1 FROM tpo.fatture_consegne fc WHERE fc.consegna_id = c.id){ESTERNE}
FROM tpo.consegne c JOIN tpo.clienti cl ON cl.id = c.cliente_id
WHERE c.stato = 'CONSEGNATA'
ORDER BY cl.denominazione, c.data_effettiva, c.public_id"""
ESTERNE_SQL = """ OR EXISTS (SELECT 1 FROM tpo.fatture_esterne_consegne x JOIN tpo.fatture_esterne fe ON fe.id = x.fattura_esterna_id
                                  WHERE x.consegna_id = c.id AND fe.tipo = 'FATTURA' AND fe.stato = 'EMESSA')"""
SQL_RIGHE = """
SELECT rc.consegna_id, v.denominazione, rc.quantita, rc.unita_misura::text, l.prezzo_unitario, l.aliquota_igic
FROM tpo.righe_consegna rc JOIN tpo.varieta v ON v.id = rc.varieta_id
LEFT JOIN tpo.listino_varieta l ON l.varieta_id = rc.varieta_id
WHERE rc.consegna_id = ANY(%s) ORDER BY rc.consegna_id, rc.posizione"""


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def _n(value) -> str:
    text = format(Decimal(value).normalize(), "f")
    return text if "." not in text else text.rstrip("0").rstrip(".")


def _euro(value: Decimal) -> str:
    return f"{value.quantize(CENT, rounding=ROUND_HALF_UP):.2f} EUR"


def _in_mese(giorno: date, mese: str) -> bool:
    return giorno.strftime("%Y-%m") == mese


def raccogli(conn, mese: str):
    """{cliente_pid: dict(nome, pk, modalita, termini, consegne=[...], gia_fatturate=[codici])} per il mese."""
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('tpo.fatture_esterne_consegne') IS NOT NULL")
    con_esterne = cur.fetchone()[0]          # registro delle fatture emesse fuori da TPO (migrazione 0040)
    cur.execute(SQL_CONSEGNE.replace("{ESTERNE}", ESTERNE_SQL if con_esterne else ""))
    per_cliente: dict[str, dict] = {}
    pks = []
    for pk, pid, cli_pk, cli_pid, nome, eff, modalita, termini, fatturata in cur.fetchall():
        giorno = eff.astimezone(TIMEZONE).date()
        if not _in_mese(giorno, mese):
            continue
        cli = per_cliente.setdefault(cli_pid, {"nome": nome, "pk": cli_pk, "modalita": modalita, "termini": termini,
                                               "consegne": [], "gia_fatturate": []})
        if fatturata:
            cli["gia_fatturate"].append(pid)
            continue
        cli["consegne"].append({"pk": pk, "pid": pid, "data": giorno, "voci": []})
        pks.append(pk)
    if pks:
        cur.execute(SQL_RIGHE, (pks,))
        righe = defaultdict(list)
        for cons_pk, var, qty, uom, prezzo, igic in cur.fetchall():
            righe[cons_pk].append((var, Decimal(qty), uom, None if prezzo is None else Decimal(prezzo),
                                   None if igic is None else Decimal(igic)))
        for cli in per_cliente.values():
            for c in cli["consegne"]:
                c["voci"] = righe.get(c["pk"], [])
    return per_cliente


def _totali(consegne):
    netto = igic = Decimal(0)
    mancanti: set[str] = set()
    for c in consegne:
        for var, qty, _uom, prezzo, aliq in c["voci"]:
            if prezzo is None or aliq is None:
                mancanti.add(var)
                continue
            riga = (qty * prezzo).quantize(CENT, rounding=ROUND_HALF_UP)
            netto += riga
            igic += (riga * aliq / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
    return netto, igic, mancanti


def _gruppi(cli):
    """Fatture da emettere: lista di liste di consegne secondo la modalita' del cliente."""
    if cli["modalita"] == "A_CONSEGNA":
        return [[c] for c in cli["consegne"]]
    return [cli["consegne"]] if cli["consegne"] else []


def _argv(cli_pid, gruppo, mese, data_emissione):
    codici = [c["pid"] for c in gruppo]
    chiave = "fatture-mese-" + hashlib.sha256((cli_pid + "|" + ",".join(sorted(codici))).encode()).hexdigest()[:16]
    argv = ["fattura", "emetti", "--client", cli_pid]
    for codice in codici:
        argv += ["--consegna", codice]
    argv += ["--data-emissione", data_emissione, "--actor", ACTOR,
             "--reason", f"Fatturazione {mese} richiesta da Matteo",
             "--correlation-id", f"fatture-{mese}-{cli_pid}", "--idempotency-key", chiave, "--confirm"]
    return argv


def _mostra(argv):
    return " ".join(a if all(ch.isalnum() or ch in "-_./:=" for ch in a) else repr(a) for a in argv)


def run(conn, mese, cliente, senza, data_emissione, esegui, esegui_tpo, out=print) -> int:
    dati = raccogli(conn, mese)
    esclusi = [_fold(s.strip()) for s in (senza or "").split(",") if s.strip()]
    out(f"== FATTURE {mese} " + ("(ESECUZIONE)" if esegui else "(ANTEPRIMA: nulla viene scritto)"))
    scelti = {k: v for k, v in dati.items() if not cliente or _fold(cliente) in _fold(v["nome"])}
    if not scelti:
        out("Nessun cliente con consegne nel mese" + (f" per '{cliente}'." if cliente else "."))
        return 0
    if esegui and (not cliente or len(scelti) != 1):
        out("STOP: per emettere indica UN solo cliente con --cliente (anche una parte del nome, che deve riconoscerne uno solo).")
        return 2
    tot_netto = Decimal(0)
    da_fare = []
    for cli_pid, cli in sorted(scelti.items(), key=lambda kv: kv[1]["nome"]):
        nome = cli["nome"]
        if any(e in _fold(nome) for e in esclusi):
            n = len(cli["consegne"])
            out(f"\n{nome} ({cli_pid}): SENZA FATTURA (escluso da te) - {n} consegne del mese lasciate cosi'.")
            continue
        netto, igic, mancanti = _totali(cli["consegne"])
        out(f"\n{nome} ({cli_pid}): {len(cli['consegne'])} consegne da fatturare"
            + (f", {len(cli['gia_fatturate'])} gia' fatturate ({', '.join(cli['gia_fatturate'])})" if cli["gia_fatturate"] else "")
            + f" - netto {_euro(netto)}, IGIC {_euro(igic)}, totale {_euro(netto + igic)}")
        for c in cli["consegne"]:
            voci = ", ".join(f"{v[0]} {_n(v[1])} {v[2]}" for v in c["voci"]) or "(nessuna riga)"
            out(f"   {c['pid']}  {c['data'].isoformat()}  {voci}")
        problemi = []
        if not cli["consegne"]:
            out("   niente da fatturare per questo mese.")
            continue
        if mancanti:
            problemi.append("listino senza prezzo per: " + ", ".join(sorted(mancanti)))
        if not cli["modalita"] or not cli["termini"]:
            problemi.append("fatturazione non configurata (modalita' / termini di pagamento)")
        if problemi:
            out("   NON EMETTIBILE: " + "; ".join(problemi))
            if not cli["modalita"] or not cli["termini"]:
                out("   Per configurarlo (scegli MODALITA = A_CONSEGNA | PERIODICA_MENSILE e GIORNI, es. 30):")
                out(f"   {RUN_REL} cliente fatturazione --client {cli_pid} --modalita-fatturazione MODALITA "
                    f"--termini-pagamento-giorni GIORNI --actor {ACTOR}")
            continue
        gruppi = _gruppi(cli)
        out(f"   EMETTIBILE: {cli['modalita']} -> {len(gruppi)} fattur{'a' if len(gruppi) == 1 else 'e'}, "
            f"scadenza a {cli['termini']} giorni dall'emissione")
        tot_netto += netto
        for g in gruppi:
            da_fare.append((cli_pid, nome, g))
            if not esegui:
                out("   " + _mostra([RUN_REL, *_argv(cli_pid, g, mese, data_emissione)]))
    if not esegui:
        out(f"\nTOTALE emettibile: {_euro(tot_netto)} netto. Per emettere: stesso comando con --cliente \"NOME\" "
            f"--data-emissione AAAA-MM-GG --esegui (un cliente alla volta).")
        return 0
    for cli_pid, nome, g in da_fare:
        codice, testo = esegui_tpo(_argv(cli_pid, g, mese, data_emissione))
        out(testo.strip())
        if codice != 0:
            out(f"\nSTOP: emissione fallita (exit {codice}) per {nome}. Le fatture gia' emesse restano valide; rilancia dopo la correzione.")
            return 1
    out(f"\nFATTO: {len(da_fare)} fattur{'a' if len(da_fare) == 1 else 'e'} emess{'a' if len(da_fare) == 1 else 'e'} per {scelti[next(iter(scelti))]['nome']}.")
    return 0


def _esegui_tpo(argv):
    done = subprocess.run([RUN, *argv], capture_output=True, text=True)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mese", default="2026-10", help="AAAA-MM (default 2026-10)")
    ap.add_argument("--cliente", help="un cliente (anche parte del nome); obbligatorio per --esegui")
    ap.add_argument("--senza-fattura", help='clienti esclusi, separati da virgola (es. "Alchimia,Oca Bianca")')
    ap.add_argument("--data-emissione", default=None, help="AAAA-MM-GG (default: oggi, fuso Canarie)")
    ap.add_argument("--esegui", action="store_true", help="emette davvero (un solo cliente)")
    a = ap.parse_args()
    try:
        datetime.strptime(a.mese, "%Y-%m")
        emissione = a.data_emissione or datetime.now(TIMEZONE).date().isoformat()
        date.fromisoformat(emissione)
    except ValueError:
        print("STOP: --mese AAAA-MM e --data-emissione AAAA-MM-GG.")
        return 2
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"], autocommit=True)
    try:
        return run(conn, a.mese, a.cliente, a.senza_fattura, emissione, a.esegui, _esegui_tpo)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
