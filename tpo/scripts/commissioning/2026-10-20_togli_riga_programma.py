"""Toglie UNA RIGA (una varieta') da un programma di fornitura ATTIVO (20/10/2026, richiesta di Matteo: Bahia Real non
ha Rabano, ha solo Afila fisso piu' due mezzi SET a giro per test catalogo; il Rabano era un segnaposto sbagliato).

Chiude la versione corrente del programma e ne apre la successiva con tutto IDENTICO (stato, ancora/giorno, righe,
ricorrenze, orario di generazione, finestra) tranne la riga tolta. Non retroattivo. Le altre righe tengono la loro
posizione. Un programma deve restare con almeno una riga (per fermarlo si sospende).

ATTENZIONE (lacuna nota, come per le quantita'): cambiare il programma NON corregge gli ordini gia' generati dallo
scheduler. Lo script li elenca (ordini APERTI/PARZIALMENTE_EVASI del programma con consegna prevista da oggi in poi che
contengono quella varieta') e stampa il comando pronto:
  - ordine APERTO a piu' righe senza consegne -> `2026-10-16_stralcia_riga.py` (nuovo ordine manuale senza la riga +
    annullo del vecchio);
  - ordine APERTO con la sola riga -> `2026-10-07_modifica_ordine.py annulla`;
  - ordine PARZIALMENTE_EVASO -> `2026-10-05_chiudi_residuo_ordini.py` (rinuncia al residuo, serve la migrazione 0039).
Gli ordini con consegna prevista prima di oggi NON vengono toccati.

Sempre in ANTEPRIMA finche' non aggiungi --esegui; tutto o niente (una transazione); audit con prima/dopo.
NON tocca ordini, consegne, stock. NON rilancia lo scheduler.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-20_togli_riga_programma.py PF-000011 Rabano \\
      --motivo "Bahia Real non ha Rabano: segnaposto sbagliato"
  ... --esegui    per scrivere davvero

Rifiuta (nulla scritto): programma inesistente o non ATTIVO; varieta' non presente (o presente piu' volte) nel
programma; programma con una sola riga.

NESSUN comando correttivo automatico: la versione precedente resta nel database con la riga e l'audit la descrive
(varieta', quantita', ricorrenza); per rimetterla serve un nuovo programma/versione deciso insieme.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

BASE = ROOT / "scripts" / "commissioning" / "2026-10-12_sposta_giorno_programma.py"
ACTOR = "matteo"
PROVENANCE = "commissioning:2026-10-20_togli_riga_programma"
MODIFICA = "scripts/commissioning/2026-10-07_modifica_ordine.py"
STRALCIA = "scripts/commissioning/2026-10-16_stralcia_riga.py"
CHIUDI_RESIDUO = "scripts/commissioning/2026-10-05_chiudi_residuo_ordini.py"


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


def ordini_con_varieta(cur, program_pk: int, da: date, varieta_id: int):
    """Ordini APERTI / PARZIALMENTE_EVASI del programma, consegna da `da` in poi, che contengono la varieta'."""
    cur.execute("""SELECT o.public_id, o.data_consegna_prevista, o.stato::text,
                          (SELECT count(*) FROM tpo.righe_ordine x WHERE x.ordine_id=o.id),
                          (SELECT count(*) FROM tpo.consegne_ordini co WHERE co.ordine_id=o.id)
                   FROM tpo.ordini o
                   WHERE o.programma_fornitura_id=%s AND o.stato IN ('APERTO','PARZIALMENTE_EVASO')
                     AND o.data_consegna_prevista >= %s
                     AND EXISTS (SELECT 1 FROM tpo.righe_ordine r WHERE r.ordine_id=o.id AND r.varieta_id=%s)
                   ORDER BY o.data_consegna_prevista, o.public_id""", (program_pk, da, varieta_id))
    return cur.fetchall()


def run(conn, programma: str, varieta: str, motivo: str, esegui: bool,
        today: date | None = None, out=print) -> int:
    b = _carica_base()
    today = today or datetime.now(b.TIMEZONE).date()
    cur = conn.cursor()
    try:
        (pk, cliente_pk, public_id, cliente, vpk, numero, stato, data_inizio, data_fine, orario, finestra,
         valida_dal) = b.carica(cur, programma)
        if stato != "ATTIVO":
            raise b.Refused(f"{public_id} e' {stato}: modifico solo un programma ATTIVO.")
        righe = b.righe_versione(cur, vpk)
        scelte = [r for r in righe if _fold(r[3]) == _fold(varieta)] or \
                 [r for r in righe if _fold(r[3]).startswith(_fold(varieta))]
        if len(scelte) != 1:
            elenco = ", ".join(r[3] for r in righe)
            raise b.Refused(f"varieta' '{varieta}': {len(scelte)} corrispondenze nel programma ({elenco}).")
        if len(righe) < 2:
            raise b.Refused(f"{public_id} ha una sola riga: per fermare il programma si sospende, non si svuota.")
        _, pos_t, var_id, nome, qty_old, uom, tipo_t, iv_t, giorni_t = scelte[0]
    except b.Refused as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2

    out(f"== TOGLI RIGA DAL PROGRAMMA {public_id} - {cliente} ({'ESECUZIONE' if esegui else 'ANTEPRIMA, NULLA VIENE SCRITTO'})")
    out(f"Versione corrente v{numero} -> nuova v{numero + 1}; viene tolta SOLO la riga {nome}; resto identico:")
    for _, pos, _, n_, q, u, tipo, iv, giorni in righe:
        marca = "   <-- TOLTA" if pos == pos_t else ""
        extra = f" giorni ISO {giorni}" if giorni else (f" ogni {iv} giorni" if iv else "")
        out(f"   {pos}. {n_} {_n(q)} {u}  {tipo}{extra}{marca}")
    out(f"\nORDINI GIA' GENERATI con {nome} (consegna prevista da oggi {today.isoformat()} in poi):")
    ordini = ordini_con_varieta(cur, pk, today, var_id)
    if not ordini:
        out("   nessuno")
    comandi = []
    for ordine, data, st, n_righe, n_consegne in ordini:
        if st == "PARZIALMENTE_EVASO":
            azione = f"{CHIUDI_RESIDUO} --ordini {ordine}"
            come = "ha consegne: si chiude il residuo (rinuncia)"
        elif n_righe > 1 and n_consegne == 0:
            azione = f"{STRALCIA} {ordine} {nome} --motivo \"{public_id}: {nome} tolto dal programma\""
            come = "toglie la riga (nuovo ordine manuale senza di essa + annullo del vecchio)"
        elif n_righe == 1 and n_consegne == 0:
            azione = f"{MODIFICA} annulla {ordine} --motivo \"{public_id}: {nome} tolto dal programma\""
            come = "ordine con la sola riga: si annulla"
        else:
            azione = None
            come = "ha consegne ma e' APERTO: caso insolito, da guardare a mano"
        out(f"   {ordine} {b._giorno(data)} {st}: {come}")
        if azione:
            comandi.append(azione)
    if comandi:
        out("   Il programma NON cambia gli ordini gia' esistenti. Dopo --esegui, anteprime di correzione:")
        for c in comandi:
            out(f"     .venv/bin/python {c}")
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
    correlation = f"togli-riga-programma-{public_id}-{uuid.uuid4().hex[:8]}"
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
            if pos == pos_t:
                continue
            cur.execute("""INSERT INTO tpo.righe_programma_fornitura
                             (programma_versione_id,posizione,varieta_id,quantita,unita_misura,tipo_ricorrenza,
                              intervallo_giorni)
                           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (new_vpk, pos, vid, qty, u, tipo, iv))
            new_riga = cur.fetchone()[0]
            if giorni_iso:
                for g in giorni_iso.split(","):
                    cur.execute("INSERT INTO tpo.righe_programma_giorni(riga_programma_id,giorno_iso) VALUES (%s,%s)",
                                (new_riga, int(g)))
        riga_tolta = {"posizione": pos_t, "varieta": nome, "quantita": _n(qty_old), "unita": uom,
                      "ricorrenza": tipo_t, "intervallo_giorni": iv_t, "giorni_iso": giorni_t or None}
        cur.execute("""INSERT INTO tpo.audit_eventi
                         (occurred_at,actor,entity_type,entity_public_id,operation,reason,before_data,after_data,
                          correlation_id,provenance)
                       VALUES (%s,%s,'PROGRAMMA_FORNITURA',%s,'UPDATE',%s,%s::jsonb,%s::jsonb,%s,%s)""",
                    (now, ACTOR, public_id, f"Tolta la riga {nome}: {motivo}",
                     json.dumps({"numero_versione": numero, "righe": len(righe), "riga_tolta": riga_tolta}),
                     json.dumps({"numero_versione": numero + 1, "righe": len(righe) - 1}),
                     correlation, PROVENANCE))
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        conn.commit()
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: {public_id} v{numero + 1} ATTIVA senza {nome}; v{numero} chiusa (resta nel database con la riga).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("programma", help="es. PF-000011")
    ap.add_argument("varieta", help="nome della varieta' da togliere, es. Rabano")
    ap.add_argument("--motivo", required=True)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, a.programma, a.varieta, a.motivo, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
