"""Aggiunge UNA RIGA (una varieta') a un programma di fornitura ATTIVO (4/11/2026, richiesta di Matteo: Splash prende
ogni settimana anche 0,5 SET di Mizuna).

Chiude la versione corrente del programma e ne apre la successiva con tutto IDENTICO (stato, ancora/giorno, righe,
ricorrenze, orario di generazione, finestra) piu' la nuova riga, in ultima posizione. La nuova riga ha la STESSA
ricorrenza della prima riga del programma (stesso tipo, stesso intervallo, stessi giorni). Non retroattivo.

ATTENZIONE (lacuna nota): aggiungere la riga NON modifica gli ordini gia' generati dallo scheduler. Lo script li elenca
(ordini APERTI del programma con consegna prevista da oggi in poi) e stampa il comando pronto per aggiungere la
varieta' a ciascuno, se esiste; altrimenti lo dice.

Sempre in ANTEPRIMA finche' non aggiungi --esegui; tutto o niente (una transazione); audit con prima/dopo.
NON tocca ordini, consegne, stock. NON rilancia lo scheduler.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-11-04_aggiungi_riga_programma.py PF-000010 Mizuna 0.5 \\
      --motivo "Splash: ogni settimana anche 0,5 SET di Mizuna"
  ... --esegui    per scrivere davvero

Rifiuta (nulla scritto): programma inesistente o non ATTIVO; varieta' sconosciuta o gia' presente nel programma;
quantita' <= 0.

COMANDO CORRETTIVO: 2026-10-20_togli_riga_programma.py con lo stesso programma e la stessa varieta'.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import unicodedata
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

BASE = ROOT / "scripts" / "commissioning" / "2026-10-12_sposta_giorno_programma.py"
ACTOR = "matteo"
PROVENANCE = "commissioning:2026-11-04_aggiungi_riga_programma"


def _carica_base():
    spec = importlib.util.spec_from_file_location("sposta_giorno_base", BASE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").strip()


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def run(conn, programma: str, varieta: str, quantita: str, motivo: str, esegui: bool,
        today: date | None = None, out=print) -> int:
    b = _carica_base()
    today = today or datetime.now(b.TIMEZONE).date()
    cur = conn.cursor()
    try:
        try:
            qty = Decimal(quantita)
        except InvalidOperation:
            raise b.Refused(f"quantita' non valida: {quantita}")
        if qty <= 0:
            raise b.Refused("la quantita' deve essere maggiore di zero.")
        (pk, cliente_pk, public_id, cliente, vpk, numero, stato, data_inizio, data_fine, orario, finestra,
         valida_dal) = b.carica(cur, programma)
        if stato != "ATTIVO":
            raise b.Refused(f"{public_id} e' {stato}: modifico solo un programma ATTIVO.")
        righe = b.righe_versione(cur, vpk)
        if not righe:
            raise b.Refused(f"{public_id} v{numero} non ha righe.")
        cur.execute("SELECT id, public_id, denominazione FROM tpo.varieta")
        trovate = [r for r in cur.fetchall() if _fold(r[2]) == _fold(varieta)]
        if len(trovate) != 1:
            raise b.Refused(f"varieta' '{varieta}' sconosciuta ({len(trovate)} corrispondenze).")
        var_id, _, nome = trovate[0]
        if any(r[2] == var_id for r in righe):
            raise b.Refused(f"{nome} e' gia' nel programma {public_id}: per cambiare la quantita' c'e' "
                            f"2026-10-14_quantita_programma.py.")
        _, _, _, _, _, _, tipo_n, iv_n, giorni_n = righe[0]
        pos_n = max(r[1] for r in righe) + 1
    except b.Refused as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2

    out(f"== AGGIUNGI RIGA AL PROGRAMMA {public_id} - {cliente} ({'ESECUZIONE' if esegui else 'ANTEPRIMA, NULLA VIENE SCRITTO'})")
    out(f"Versione corrente v{numero} -> nuova v{numero + 1}; viene aggiunta SOLO la riga {nome}; resto identico:")
    for _, pos, _, n_, q, u, tipo, iv, giorni in righe:
        extra = f" giorni ISO {giorni}" if giorni else (f" ogni {iv} giorni" if iv else "")
        out(f"   {pos}. {n_} {_n(q)} {u}  {tipo}{extra}")
    extra_n = f" giorni ISO {giorni_n}" if giorni_n else (f" ogni {iv_n} giorni" if iv_n else "")
    out(f"   {pos_n}. {nome} {_n(qty)} SET  {tipo_n}{extra_n}   <-- NUOVA (stessa ricorrenza della prima riga)")
    out(f"\nORDINI GIA' GENERATI del programma (consegna prevista da oggi {today.isoformat()} in poi), NON cambiano:")
    ordini = b.ordini_aperti(cur, pk, today)
    if not ordini:
        out("   nessuno")
    for ordine, data, st, righe_txt in ordini:
        out(f"   {ordine} {b._giorno(data)} {st}: {righe_txt}")
    if ordini:
        out(f"   Una riga NON si puo' aggiungere a un ordine esistente (modifica_ordine cambia solo quantita', annulla, data): la nuova varieta' si copre con un ordine manuale a parte.")
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
    correlation = f"aggiungi-riga-programma-{public_id}-{uuid.uuid4().hex[:8]}"
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

        def copia_riga(pos, vid, q, u, tipo, iv, giorni_iso):
            cur.execute("""INSERT INTO tpo.righe_programma_fornitura
                             (programma_versione_id,posizione,varieta_id,quantita,unita_misura,tipo_ricorrenza,
                              intervallo_giorni)
                           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (new_vpk, pos, vid, q, u, tipo, iv))
            new_riga = cur.fetchone()[0]
            if giorni_iso:
                for g in str(giorni_iso).split(","):
                    cur.execute("INSERT INTO tpo.righe_programma_giorni(riga_programma_id,giorno_iso) VALUES (%s,%s)",
                                (new_riga, int(g)))

        for _, pos, vid, _, q, u, tipo, iv, giorni_iso in righe:
            copia_riga(pos, vid, q, u, tipo, iv, giorni_iso)
        copia_riga(pos_n, var_id, qty, "SET", tipo_n, iv_n, giorni_n)
        riga_nuova = {"posizione": pos_n, "varieta": nome, "quantita": _n(qty), "unita": "SET",
                      "ricorrenza": tipo_n, "intervallo_giorni": iv_n, "giorni_iso": giorni_n or None}
        cur.execute("""INSERT INTO tpo.audit_eventi
                         (occurred_at,actor,entity_type,entity_public_id,operation,reason,before_data,after_data,
                          correlation_id,provenance)
                       VALUES (%s,%s,'PROGRAMMA_FORNITURA',%s,'UPDATE',%s,%s::jsonb,%s::jsonb,%s,%s)""",
                    (now, ACTOR, public_id, f"Aggiunta la riga {nome}: {motivo}",
                     json.dumps({"numero_versione": numero, "righe": len(righe)}),
                     json.dumps({"numero_versione": numero + 1, "righe": len(righe) + 1, "riga_nuova": riga_nuova}),
                     correlation, PROVENANCE))
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        conn.commit()
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: {public_id} v{numero + 1} ATTIVA con {nome} {_n(qty)} SET; v{numero} chiusa (resta nel database).")
    out(f"COMANDO CORRETTIVO: .venv/bin/python scripts/commissioning/2026-10-20_togli_riga_programma.py "
        f"{public_id} {nome} --motivo \"annullo aggiunta {nome}\" --esegui")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("programma", help="es. PF-000010")
    ap.add_argument("varieta", help="nome della varieta' da aggiungere, es. Mizuna")
    ap.add_argument("quantita", help="SET per consegna, es. 0.5")
    ap.add_argument("--motivo", required=True)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, a.programma, a.varieta, a.quantita, a.motivo, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
