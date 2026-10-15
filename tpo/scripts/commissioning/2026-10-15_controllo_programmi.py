"""SOLA LETTURA - controlla che gli ORDINI gia' generati corrispondano ai PROGRAMMI DI FORNITURA correnti (15/10/2026).

Perche': cambiare un programma (quantita', giorno, righe) NON corregge gli ordini gia' generati dallo scheduler.
Finora i disallineamenti si cercavano a mano; questo comando li trova tutti e stampa i comandi pronti.

Per ogni programma con versione corrente (ATTIVO) ricalcola, con le STESSE regole dello scheduler, le consegne attese
da oggi fino a oggi + finestra operativa e le confronta con gli ordini del programma (non annullati):

  MANCA       consegna attesa senza nessun ordine (il prossimo giro dello scheduler dovrebbe crearlo; se la data e'
              l'ultima della finestra e l'orario di generazione non e' ancora passato: "non ancora generato")
  NON PREVISTO ordine APERTO/PARZIALMENTE_EVASO a una data in cui il programma non ricorre (programma spostato o
              vecchio ritmo) -> anteprima di annullamento (ma se lo consegni in anticipo, NON annullare: lega la
              consegna all'ordine)
  QUANTITA'   riga dell'ordine con quantita' diversa dal programma -> anteprima `modifica_ordine.py quantita`
  RIGHE       varieta' in piu' o in meno rispetto al programma (nessun comando automatico: per togliere UNA riga serve
              un cambio di schema; decidi tu)
  DOPPIO      piu' ordini non annullati dello stesso programma nella stessa data

Per i programmi SOSPESI/CESSATI elenca gli ordini ancora aperti da oggi in poi (domanda fantasma).
In piu', informativo: ordini aperti del programma con consegna prevista GIA' PASSATA.

ATTENZIONE (rischio noto): l'idempotenza dello scheduler e' calcolata sulle righe dell'ordine; se correggi a mano la
quantita' di un ordine, una nuova esecuzione dello scheduler potrebbe non riconoscerlo e rigenerarlo. Questo comando
segnala il caso come DOPPIO se succede.

Non scrive nulla. Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-15_controllo_programmi.py            # tutti i programmi
  .venv/bin/python scripts/commissioning/2026-10-15_controllo_programmi.py PF-000010  # uno solo
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

TIMEZONE = ZoneInfo("Atlantic/Canary")
GIORNI = ["lunedi'", "martedi'", "mercoledi'", "giovedi'", "venerdi'", "sabato", "domenica"]
MODIFICA = "scripts/commissioning/2026-10-07_modifica_ordine.py"
APERTI = ("APERTO", "PARZIALMENTE_EVASO")


def _giorno(d: date) -> str:
    return f"{GIORNI[d.weekday()]} {d.isoformat()}"


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def ricorre(tipo: str, intervallo, ancora: date, data: date, giorni_iso: set[int]) -> bool:
    """Stessa regola di application/scheduling/engine.py::_ricorre."""
    giorni = (data - ancora).days
    if giorni < 0:
        return False
    if tipo == "SETTIMANALE":
        return giorni % 7 == 0
    if tipo == "QUINDICINALE":
        return giorni % 15 == 0
    if tipo == "MENSILE":
        return data.day == ancora.day
    if tipo == "OGNI_X_GIORNI":
        return giorni % int(intervallo) == 0
    return data.isoweekday() in giorni_iso            # GIORNI_SETTIMANA


def attese(righe, data_inizio: date, data_fine, da: date, a: date):
    """{data: {varieta_id: (nome, quantita_totale, unita)}} per le consegne attese tra da e a (estremi inclusi)."""
    out: dict[date, dict[int, list]] = {}
    d = da
    while d <= a:
        if d >= data_inizio and (data_fine is None or d <= data_fine):
            for var_id, nome, qty, uom, tipo, iv, giorni in righe:
                if ricorre(tipo, iv, data_inizio, d, giorni):
                    slot = out.setdefault(d, {}).setdefault(var_id, [nome, Decimal(0), uom])
                    slot[1] += Decimal(qty)
        d += timedelta(days=1)
    return out


def _programmi(cur, solo: str | None):
    cur.execute("""SELECT p.id, p.public_id, c.denominazione, pv.numero_versione, pv.stato::text, pv.data_inizio,
                          pv.data_fine, pv.orario_generazione, pv.finestra_operativa_giorni, pv.id
                   FROM tpo.programmi_fornitura p JOIN tpo.clienti c ON c.id=p.cliente_id
                   JOIN tpo.programmi_fornitura_versioni pv ON pv.programma_fornitura_id=p.id
                   WHERE pv.valida_al IS NULL AND pv.voided_at IS NULL AND (%s::text IS NULL OR p.public_id=%s)
                   ORDER BY p.public_id""", (solo, solo))
    return cur.fetchall()


def _righe(cur, vpk: int):
    cur.execute("""SELECT r.varieta_id, v.denominazione, r.quantita, r.unita_misura::text, r.tipo_ricorrenza::text,
                          r.intervallo_giorni,
                          COALESCE((SELECT array_agg(g.giorno_iso) FROM tpo.righe_programma_giorni g
                                    WHERE g.riga_programma_id=r.id), ARRAY[]::int[])
                   FROM tpo.righe_programma_fornitura r JOIN tpo.varieta v ON v.id=r.varieta_id
                   WHERE r.programma_versione_id=%s ORDER BY r.posizione""", (vpk,))
    return [(a, b, c, d, e, f, set(g)) for a, b, c, d, e, f, g in cur.fetchall()]


def _ordini(cur, ppk: int):
    """Ordini non annullati del programma, con le righe: {ordine: (data, stato, [(var_id, nome, qty, uom)])}."""
    cur.execute("""SELECT o.public_id, o.data_consegna_prevista, o.stato::text, ro.varieta_id, v.denominazione,
                          ro.quantita, ro.unita_misura::text
                   FROM tpo.ordini o LEFT JOIN tpo.righe_ordine ro ON ro.ordine_id=o.id
                   LEFT JOIN tpo.varieta v ON v.id=ro.varieta_id
                   WHERE o.programma_fornitura_id=%s AND o.stato <> 'ANNULLATO'
                   ORDER BY o.data_consegna_prevista, o.public_id, ro.posizione""", (ppk,))
    ordini: dict[str, list] = {}
    for oid, data, stato, var_id, nome, qty, uom in cur.fetchall():
        slot = ordini.setdefault(oid, [data, stato, []])
        if var_id is not None:
            slot[2].append((var_id, nome, Decimal(qty), uom))
    return ordini


def controlla_programma(cur, prog, adesso: datetime, out) -> int:
    """Stampa le differenze di un programma; restituisce quante ne ha trovate."""
    ppk, pid, cliente, numero, stato, data_inizio, data_fine, orario, finestra, vpk = prog
    oggi = adesso.date()
    ordini = _ordini(cur, ppk)
    righe_out: list[str] = []

    if stato != "ATTIVO":
        for oid, (data, st, righe) in ordini.items():
            if st in APERTI and data >= oggi:
                testo = ", ".join(f"{n} {_n(q)}" for _, n, q, _ in righe)
                righe_out.append(f"   FANTASMA  {oid} {_giorno(data)} {st}: {testo}  (programma {stato})")
                righe_out.append(f"      .venv/bin/python {MODIFICA} annulla {oid} "
                                 f"--motivo \"Programma {pid} {stato}: ordine rimasto aperto\"")
        n = sum(1 for r in righe_out if "FANTASMA" in r)
        if righe_out:
            out(f"\n-- {pid} - {cliente}: programma {stato}, ma ci sono ordini aperti")
            for r in righe_out:
                out(r)
        return n

    fine_finestra = oggi + timedelta(days=int(finestra))
    righe = _righe(cur, vpk)
    previste = attese(righe, data_inizio, data_fine, oggi, fine_finestra)
    per_data: dict[date, list] = defaultdict(list)
    for oid, (data, st, rg) in ordini.items():
        per_data[data].append((oid, st, rg))
    problemi = 0
    date_toccate = sorted(set(previste) | {d for d in per_data if d >= oggi})
    for d in date_toccate:
        presenti = per_data.get(d, [])
        attesa = previste.get(d)
        if attesa and not presenti:
            ultimo_non_generato = d == fine_finestra and adesso.time().replace(tzinfo=None) < orario
            if ultimo_non_generato:
                righe_out.append(f"   (info)    {_giorno(d)}: non ancora generato (lo scheduler genera dopo le {orario:%H:%M})")
            else:
                problemi += 1
                testo = ", ".join(f"{v[0]} {_n(v[1])}" for v in attesa.values())
                righe_out.append(f"   MANCA     {_giorno(d)}: previsto {testo}, nessun ordine")
            continue
        if not attesa:
            for oid, st, rg in presenti:
                if st in APERTI and d >= oggi:
                    problemi += 1
                    testo = ", ".join(f"{n} {_n(q)}" for _, n, q, _ in rg)
                    righe_out.append(f"   NON PREVISTO  {oid} {_giorno(d)} {st}: {testo}  (il programma non ricorre quel giorno)")
                    righe_out.append(f"      .venv/bin/python {MODIFICA} annulla {oid} "
                                     f"--motivo \"{pid}: ordine di un vecchio ritmo, non piu' previsto\"")
            continue
        if len(presenti) > 1:
            problemi += 1
            elenco = "; ".join(f"{oid} {st} ({', '.join(f'{n} {_n(q)}' for _, n, q, _ in rg)})" for oid, st, rg in presenti)
            righe_out.append(f"   DOPPIO    {_giorno(d)}: {len(presenti)} ordini per lo stesso giorno: {elenco}")
            continue
        oid, st, rg = presenti[0]
        reali: dict[int, list] = {}
        for var_id, nome, qty, uom in rg:
            slot = reali.setdefault(var_id, [nome, Decimal(0)])
            slot[1] += qty
        for var_id, (nome, qty, uom) in attesa.items():
            if var_id not in reali:
                problemi += 1
                righe_out.append(f"   RIGHE     {oid} {_giorno(d)}: manca {nome} {_n(qty)} {uom} (previsto dal programma)")
            elif reali[var_id][1] != qty:
                problemi += 1
                righe_out.append(f"   QUANTITA' {oid} {_giorno(d)} {st}: {nome} {_n(reali[var_id][1])} -> programma {_n(qty)}")
                if st == "APERTO":
                    righe_out.append(f"      .venv/bin/python {MODIFICA} quantita {oid} {nome} {_n(qty)} "
                                     f"--motivo \"{pid}: {nome} da {_n(reali[var_id][1])} a {_n(qty)} come da programma\"")
                else:
                    righe_out.append(f"      ({oid} e' {st}: la quantita' non si modifica con lo script; decidi tu)")
        for var_id, (nome, qty) in reali.items():
            if var_id not in attesa:
                problemi += 1
                righe_out.append(f"   RIGHE     {oid} {_giorno(d)}: ha {nome} {_n(qty)} che il programma non prevede")
    passati = [(oid, d_, st, rg) for oid, (d_, st, rg) in ordini.items() if st in APERTI and d_ < oggi]
    for oid, d_, st, rg in passati:
        testo = ", ".join(f"{n} {_n(q)}" for _, n, q, _ in rg)
        righe_out.append(f"   (info)    {oid} {_giorno(d_)} {st}: consegna prevista gia' passata - {testo}")
    if problemi or righe_out:
        intestazione = f"\n-- {pid} - {cliente} (v{numero}, finestra {finestra} giorni)"
        out(intestazione)
        for r in righe_out:
            out(r)
    return problemi


def run(conn, solo: str | None = None, adesso: datetime | None = None, out=print) -> int:
    adesso = adesso or datetime.now(TIMEZONE)
    cur = conn.cursor()
    programmi = _programmi(cur, solo)
    if solo and not programmi:
        out(f"STOP: programma {solo} inesistente o senza versione corrente.")
        return 2
    out(f"== CONTROLLO PROGRAMMI / ORDINI del {adesso:%Y-%m-%d %H:%M} (SOLA LETTURA, NULLA SCRITTO)")
    totale = 0
    puliti = []
    for prog in programmi:
        buffer: list[str] = []
        n = controlla_programma(cur, prog, adesso, buffer.append)
        if buffer:
            for riga in buffer:
                out(riga)
        else:
            puliti.append(f"{prog[1]} {prog[2]}")
        totale += n
    if puliti:
        out(f"\nCOERENTI ({len(puliti)}): " + "; ".join(puliti))
    out(f"\n{len(programmi)} programmi controllati, {totale} differenze da sistemare." if totale
        else f"\n{len(programmi)} programmi controllati: nessuna differenza.")
    if totale:
        out("I comandi stampati sono ANTEPRIME (senza --esegui): controlla e poi aggiungi --esegui.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("programma", nargs="?", help="es. PF-000010 (senza: tutti)")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"], autocommit=True)
    try:
        return run(conn, a.programma)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
