"""Cambia la QUANTITA' di una riga di un programma di fornitura (14/10/2026, richiesta di Matteo: Splash passa a
1,5 SET di Cilantro a ogni consegna, a partire dalla prossima).

Chiude la versione corrente del programma e ne apre la successiva con tutto IDENTICO (stato, ancora/giorno, righe,
ricorrenze, orario di generazione, finestra) tranne la quantita' della riga indicata. Non retroattivo.

ATTENZIONE (lacuna nota): cambiare il programma NON corregge gli ordini gia' generati dallo scheduler. Lo script li
elenca (ordini APERTI/PARZIALMENTE_EVASI del programma con consegna prevista da oggi in poi) e, per quelli la cui riga ha
una quantita' diversa dalla nuova, stampa il comando pronto di `2026-10-07_modifica_ordine.py quantita ...`
(anteprima). Gli ordini con consegna prevista prima di oggi (es. la parte residua di un ordine gia' consegnato a meta')
NON vengono toccati.

Sempre in ANTEPRIMA finche' non aggiungi --esegui; tutto o niente (una transazione); audit con prima/dopo.
NON tocca ordini, consegne, stock. NON rilancia lo scheduler.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-14_quantita_programma.py PF-000010 Cilantro 1.5 \\
      --motivo "Splash: da 1 a 1,5 SET di Cilantro a ogni consegna"
  ... --esegui    per scrivere davvero

Rifiuta (nulla scritto): programma inesistente o non ATTIVO; varieta' non presente (o presente piu' volte) nel
programma; quantita' <= 0 o uguale all'attuale; unita' diversa da SET.

COMANDO CORRETTIVO (stampato a fine esecuzione): lo stesso script con la quantita' precedente.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

BASE = ROOT / "scripts" / "commissioning" / "2026-10-12_sposta_giorno_programma.py"
ACTOR = "matteo"
PROVENANCE = "commissioning:2026-10-14_quantita_programma"
SELF = "scripts/commissioning/2026-10-14_quantita_programma.py"
MODIFICA = "scripts/commissioning/2026-10-07_modifica_ordine.py"


def _carica_base():
    spec = importlib.util.spec_from_file_location("sposta_giorno_base", BASE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def righe_ordini(cur, program_pk: int, da: date, varieta_id: int):
    cur.execute("""SELECT o.public_id, o.data_consegna_prevista, o.stato::text, ro.public_id, ro.quantita
                   FROM tpo.ordini o JOIN tpo.righe_ordine ro ON ro.ordine_id=o.id
                   WHERE o.programma_fornitura_id=%s AND o.stato IN ('APERTO','PARZIALMENTE_EVASO')
                     AND o.data_consegna_prevista >= %s AND ro.varieta_id=%s
                   ORDER BY o.data_consegna_prevista, o.public_id""", (program_pk, da, varieta_id))
    return cur.fetchall()


def run(conn, programma: str, varieta: str, quantita: Decimal, motivo: str, esegui: bool,
        today: date | None = None, out=print) -> int:
    b = _carica_base()
    today = today or datetime.now(b.TIMEZONE).date()
    cur = conn.cursor()
    try:
        (pk, cliente_pk, public_id, cliente, vpk, numero, stato, data_inizio, data_fine, orario, finestra,
         valida_dal) = b.carica(cur, programma)
        if stato != "ATTIVO":
            raise b.Refused(f"{public_id} e' {stato}: modifico solo un programma ATTIVO.")
        if quantita <= 0:
            raise b.Refused("la quantita' deve essere maggiore di zero (per fermare il programma si sospende).")
        righe = b.righe_versione(cur, vpk)
        scelte = [r for r in righe if _fold(r[3]) == _fold(varieta)] or \
                 [r for r in righe if _fold(r[3]).startswith(_fold(varieta))]
        if len(scelte) != 1:
            elenco = ", ".join(r[3] for r in righe)
            raise b.Refused(f"varieta' '{varieta}': {len(scelte)} corrispondenze nel programma ({elenco}).")
        _, pos_t, var_id, nome, qty_old, uom, _, _, _ = scelte[0]
        if uom != "SET":
            raise b.Refused(f"{nome}: unita' {uom}, qui gestisco solo SET.")
        if qty_old == quantita:
            raise b.Refused(f"{nome} e' gia' {_n(quantita)} SET nella versione corrente.")
    except b.Refused as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2

    out(f"== QUANTITA' PROGRAMMA {public_id} - {cliente} ({'ESECUZIONE' if esegui else 'ANTEPRIMA, NULLA VIENE SCRITTO'})")
    out(f"Versione corrente v{numero} -> nuova v{numero + 1}; cambia SOLO {nome}: {_n(qty_old)} -> {_n(quantita)} SET; "
        "resto identico:")
    for _, pos, _, n_, q, u, tipo, iv, _ in righe:
        marca = f"   <-- {_n(q)} diventa {_n(quantita)}" if pos == pos_t else ""
        out(f"   {pos}. {n_} {_n(q)} {u}  {tipo}{f' ogni {iv} giorni' if iv else ''}{marca}")
    ritmi = [(t, iv) for _, _, _, _, _, _, t, iv, g in righe if not g]
    settimana = {int(x) for *_, g in righe if g for x in g.split(",")}   # giorni ISO espliciti (1=lunedi')
    prossime, d, da = [], today + timedelta(days=1), today + timedelta(days=1)
    while len(prossime) < 4 and (d - da).days <= 120:
        if d.isoweekday() in settimana or any(b.ricorre(t, iv, data_inizio, d) for t, iv in ritmi):
            prossime.append(d)
        d += timedelta(days=1)
    out("PROSSIME CONSEGNE DEL PROGRAMMA: " + ", ".join(b._giorno(x) for x in prossime))
    out(f"\nORDINI GIA' GENERATI con {nome} (consegna prevista da oggi {today.isoformat()} in poi):")
    ordini = righe_ordini(cur, pk, today, var_id)
    da_correggere = []
    if not ordini:
        out("   nessuno")
    for ordine, data, st, riga, q in ordini:
        if q == quantita:
            out(f"   {ordine} {b._giorno(data)} {st}: {nome} {_n(q)} -> gia' giusto")
        else:
            out(f"   {ordine} {b._giorno(data)} {st}: {nome} {_n(q)} -> da portare a {_n(quantita)}")
            da_correggere.append(ordine)
    if da_correggere:
        out("   Il programma NON cambia gli ordini gia' esistenti. Dopo --esegui, anteprime di correzione:")
        for ordine in da_correggere:
            out(f"     .venv/bin/python {MODIFICA} quantita {ordine} {nome} {_n(quantita)} "
                f"--motivo \"{public_id}: {nome} da {_n(qty_old)} a {_n(quantita)} SET per consegna\"")
    out(f"\nMotivo registrato: {motivo}")
    if not esegui:
        conn.rollback()
        out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        return 0

    now = datetime.now(timezone.utc)
    if now <= valida_dal:
        conn.rollback()
        out("RIFIUTATO, nulla scritto: l'istante di adesso non e' dopo l'inizio della versione corrente.")
        return 2
    correlation = f"quantita-programma-{public_id}-{uuid.uuid4().hex[:8]}"
    try:
        cur.execute("UPDATE tpo.programmi_fornitura_versioni SET valida_al=%s WHERE id=%s AND valida_al IS NULL",
                    (now, vpk))
        if cur.rowcount != 1:
            raise RuntimeError("conflitto: la versione corrente e' cambiata nel frattempo, riprova.")
        cur.execute("""INSERT INTO tpo.programmi_fornitura_versioni
                         (programma_fornitura_id,cliente_id,numero_versione,stato,data_inizio,data_fine,
                          orario_generazione,finestra_operativa_giorni,valida_dal,valida_al,created_by)
                       VALUES (%s,%s,%s,'ATTIVO',%s,%s,%s,%s,%s,NULL,%s) RETURNING id""",
                    (pk, cliente_pk, numero + 1, data_inizio, data_fine, orario, finestra, now, ACTOR))
        new_vpk = cur.fetchone()[0]
        for old_id, pos, vid, _, qty, u, tipo, iv, giorni_iso in righe:
            cur.execute("""INSERT INTO tpo.righe_programma_fornitura
                             (programma_versione_id,posizione,varieta_id,quantita,unita_misura,tipo_ricorrenza,
                              intervallo_giorni)
                           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (new_vpk, pos, vid, quantita if pos == pos_t else qty, u, tipo, iv))
            new_riga = cur.fetchone()[0]
            if giorni_iso:
                for g in giorni_iso.split(","):
                    cur.execute("INSERT INTO tpo.righe_programma_giorni(riga_programma_id,giorno_iso) VALUES (%s,%s)",
                                (new_riga, int(g)))
        cur.execute("""INSERT INTO tpo.audit_eventi
                         (occurred_at,actor,entity_type,entity_public_id,operation,reason,before_data,after_data,
                          correlation_id,provenance)
                       VALUES (%s,%s,'PROGRAMMA_FORNITURA',%s,'UPDATE',%s,%s::jsonb,%s::jsonb,%s,%s)""",
                    (now, ACTOR, public_id, f"Cambio quantita' di {nome}: {motivo}",
                     json.dumps({"numero_versione": numero, "varieta": nome, "quantita": _n(qty_old)}),
                     json.dumps({"numero_versione": numero + 1, "varieta": nome, "quantita": _n(quantita)}),
                     correlation, PROVENANCE))
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        conn.commit()
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: {public_id} v{numero + 1} ATTIVA con {nome} {_n(quantita)} SET; v{numero} chiusa.")
    out("\n== COMANDO CORRETTIVO (torna alla quantita' precedente, nuova versione):")
    out(f"   .venv/bin/python {SELF} {public_id} {nome} {_n(qty_old)} "
        f"--motivo \"Ripristino della quantita' precedente\" --esegui")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("programma", help="es. PF-000010")
    ap.add_argument("varieta", help="nome della varieta' nel programma, es. Cilantro")
    ap.add_argument("quantita", help="nuova quantita' in SET, es. 1.5")
    ap.add_argument("--motivo", required=True)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    try:
        q = Decimal(a.quantita.replace(",", "."))
    except InvalidOperation:
        raise SystemExit(f"STOP: quantita' '{a.quantita}' non valida.")
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, a.programma, a.varieta, q, a.motivo, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
