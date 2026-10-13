"""Sposta il GIORNO di consegna di un programma di fornitura ricorrente (12/10/2026, richiesta di Matteo: La Jaira
da martedi' a lunedi', consegna anticipata al 12/10 su richiesta del cliente).

Come funziona il ritmo: ogni riga OGNI_X_GIORNI ricorre quando (data - data_inizio) e' multiplo dell'intervallo, quindi il
giorno della settimana dipende SOLO da `data_inizio` della versione. Questo script chiude la versione corrente e ne apre
la successiva (stato, righe, quantita', intervalli, orario di generazione e finestra IDENTICI) con `data_inizio` = la
nuova ancora. Niente altro cambia.

Esempio La Jaira (PF-000008, ogni 14 giorni, ancora 1/9 = martedi'): la consegna del 12/10 e' gia' fatta (ORD-000038
evaso), quindi la nuova ancora e' la PRIMA consegna col nuovo giorno: 2026-10-26 (lunedi') -> 26/10, 9/11, ...
(lunedi'), non piu' 27/10. Con l'ancora al 26/10 lo spostamento vale dalla consegna successiva e nessuna occorrenza
cade oggi (nessun rischio che uno scheduler lanciato oggi generi un ordine per il 12/10).

Sempre in ANTEPRIMA finche' non aggiungi --esegui; tutto o niente (una transazione); audit con prima/dopo.
NON tocca ordini, consegne, stock. Gli ordini gia' generati dallo scheduler con il vecchio ritmo restano aperti: lo
script li elenca e, per quelli che con il nuovo ritmo non ricorrono piu', stampa il comando di annullamento pronto.
NON rilancia lo scheduler: i nuovi ordini li genera quello delle 05:00 (la chiave di idempotenza non dipende dalla
versione, quindi gli ordini gia' esistenti non vengono duplicati).

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-12_sposta_giorno_programma.py PF-000008 \\
      --nuova-ancora 2026-10-26 --motivo "La Jaira: consegna da martedi' a lunedi' su richiesta del cliente"
  ... --esegui    per scrivere davvero

Rifiuta (nulla scritto): programma inesistente o non ATTIVO; nuova ancora uguale all'attuale o oltre la data_fine;
righe con giorni della settimana espliciti (l'ancora non conta); nuova ancora nel futuro oltre la finestra.

COMANDO CORRETTIVO (stampato a fine esecuzione): lo stesso script con --nuova-ancora <ancora precedente>.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

ACTOR = "matteo"
TIMEZONE = ZoneInfo("Atlantic/Canary")
PROVENANCE = "commissioning:2026-10-12_sposta_giorno_programma"
SELF = "scripts/commissioning/2026-10-12_sposta_giorno_programma.py"
GIORNI = ["lunedi'", "martedi'", "mercoledi'", "giovedi'", "venerdi'", "sabato", "domenica"]
RITMI_CON_ANCORA = {"OGNI_X_GIORNI", "SETTIMANALE", "QUINDICINALE", "MENSILE"}


class Refused(Exception):
    pass


def _giorno(d: date) -> str:
    return f"{GIORNI[d.weekday()]} {d.isoformat()}"


def ricorre(tipo: str, intervallo, ancora: date, data: date) -> bool:
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
    return False


def prossime(righe, ancora: date, da: date, quante: int = 4, orizzonte: int = 120) -> list[date]:
    out = []
    d = da
    while len(out) < quante and (d - da).days <= orizzonte:
        if any(ricorre(tipo, iv, ancora, d) for tipo, iv in righe):
            out.append(d)
        d += timedelta(days=1)
    return out


def carica(cur, programma: str):
    cur.execute("""SELECT p.id, p.cliente_id, p.public_id, c.denominazione, pv.id, pv.numero_versione, pv.stato::text,
                          pv.data_inizio, pv.data_fine, pv.orario_generazione, pv.finestra_operativa_giorni, pv.valida_dal
                   FROM tpo.programmi_fornitura p JOIN tpo.clienti c ON c.id=p.cliente_id
                   JOIN tpo.programmi_fornitura_versioni pv ON pv.programma_fornitura_id=p.id
                   WHERE p.public_id=%s AND pv.valida_al IS NULL AND pv.voided_at IS NULL
                   FOR UPDATE OF p, pv""", (programma,))
    row = cur.fetchone()
    if row is None:
        raise Refused(f"programma {programma} inesistente o senza versione corrente.")
    return row


def righe_versione(cur, version_pk: int):
    cur.execute("""SELECT r.id, r.posizione, r.varieta_id, v.denominazione, r.quantita, r.unita_misura::text,
                          r.tipo_ricorrenza::text, r.intervallo_giorni,
                          COALESCE((SELECT string_agg(g.giorno_iso::text, ',') FROM tpo.righe_programma_giorni g
                                    WHERE g.riga_programma_id=r.id),'')
                   FROM tpo.righe_programma_fornitura r JOIN tpo.varieta v ON v.id=r.varieta_id
                   WHERE r.programma_versione_id=%s ORDER BY r.posizione""", (version_pk,))
    return cur.fetchall()


def ordini_aperti(cur, program_pk: int, da: date):
    cur.execute("""SELECT o.public_id, o.data_consegna_prevista, o.stato::text,
                          COALESCE((SELECT string_agg(v.denominazione||' '||ro.quantita::numeric(20,2)::text, ', '
                                                      ORDER BY ro.posizione)
                                    FROM tpo.righe_ordine ro JOIN tpo.varieta v ON v.id=ro.varieta_id
                                    WHERE ro.ordine_id=o.id),'')
                   FROM tpo.ordini o
                   WHERE o.programma_fornitura_id=%s AND o.stato IN ('APERTO','PARZIALMENTE_EVASO')
                     AND o.data_consegna_prevista >= %s ORDER BY o.data_consegna_prevista, o.public_id""",
                (program_pk, da))
    return cur.fetchall()


def run(conn, programma: str, nuova: date, motivo: str, esegui: bool, today: date | None = None, out=print) -> int:
    today = today or datetime.now(TIMEZONE).date()
    cur = conn.cursor()
    try:
        (pk, cliente_pk, public_id, cliente, vpk, numero, stato, data_inizio, data_fine, orario, finestra,
         valida_dal) = carica(cur, programma)
        if stato != "ATTIVO":
            raise Refused(f"{public_id} e' {stato}: sposto il giorno solo di un programma ATTIVO.")
        if nuova == data_inizio:
            raise Refused(f"la nuova ancora {nuova} e' gia' quella della versione corrente.")
        if data_fine is not None and nuova > data_fine:
            raise Refused(f"la nuova ancora {nuova} e' dopo la data_fine {data_fine}.")
        if nuova > today + timedelta(days=int(finestra)):
            raise Refused(f"la nuova ancora {nuova} e' oltre la finestra operativa ({finestra} giorni).")
        righe = righe_versione(cur, vpk)
        if not righe:
            raise Refused(f"{public_id} v{numero} non ha righe.")
        for _, pos, _, nome, _, _, tipo, _, giorni_iso in righe:
            if tipo not in RITMI_CON_ANCORA or giorni_iso:
                raise Refused(f"la riga {pos} ({nome}) ha ricorrenza {tipo} con giorni espliciti: l'ancora non conta, "
                              "questo script non e' lo strumento giusto.")
    except Refused as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2

    ritmi = [(tipo, iv) for _, _, _, _, _, _, tipo, iv, _ in righe]
    domani = today + timedelta(days=1)          # oggi e' gia' passato: si guarda da domani
    prima = prossime(ritmi, data_inizio, domani)
    dopo = prossime(ritmi, nuova, domani)
    out(f"== SPOSTA GIORNO PROGRAMMA {public_id} - {cliente} ({'ESECUZIONE' if esegui else 'ANTEPRIMA, NULLA VIENE SCRITTO'})")
    out(f"Versione corrente v{numero} (ATTIVO, generazione {orario}, finestra {finestra} giorni): ancora {_giorno(data_inizio)}")
    out(f"Nuova versione v{numero + 1}: ancora {_giorno(nuova)}; tutto il resto identico:")
    for _, pos, _, nome, qty, uom, tipo, iv, _ in righe:
        out(f"   {pos}. {nome} {format(qty.normalize(), 'f')} {uom}  {tipo}{f' ogni {iv} giorni' if iv else ''}")
    out(f"\nPROSSIME CONSEGNE  prima: {', '.join(_giorno(d) for d in prima)}")
    out(f"                   dopo : {', '.join(_giorno(d) for d in dopo)}")
    ordini = ordini_aperti(cur, pk, today)
    stantii = []
    out("\nORDINI APERTI DI QUESTO PROGRAMMA (da oggi in poi):")
    if not ordini:
        out("   nessuno")
    for ordine, data, st, righe_txt in ordini:
        coerente = any(ricorre(t, iv, nuova, data) for t, iv in ritmi)
        out(f"   {ordine} {_giorno(data)} {st}: {righe_txt}  -> "
            + ("coerente col nuovo ritmo" if coerente else "NON ricorre piu' col nuovo ritmo"))
        if not coerente:
            stantii.append((ordine, data))
    if stantii:
        out("   Gli ordini 'NON ricorre piu'' restano aperti (domanda fantasma) se non li gestisci. Se sono davvero da "
            "togliere (di solito perche' li consegni in anticipo in un'altra consegna: in quel caso lega la consegna "
            "all'ordine e NON annullare), anteprima di annullamento:")
        for ordine, _ in stantii:
            out(f"     .venv/bin/python scripts/commissioning/2026-10-07_modifica_ordine.py annulla {ordine} "
                f"--motivo \"Programma {public_id} spostato al {GIORNI[nuova.weekday()]}: ordine del vecchio ritmo\"")
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
    correlation = f"sposta-giorno-{public_id}-{nuova.isoformat()}-{uuid.uuid4().hex[:8]}"
    try:
        cur.execute("UPDATE tpo.programmi_fornitura_versioni SET valida_al=%s WHERE id=%s AND valida_al IS NULL",
                    (now, vpk))
        if cur.rowcount != 1:
            raise RuntimeError("conflitto: la versione corrente e' cambiata nel frattempo, riprova.")
        cur.execute("""INSERT INTO tpo.programmi_fornitura_versioni
                         (programma_fornitura_id,cliente_id,numero_versione,stato,data_inizio,data_fine,
                          orario_generazione,finestra_operativa_giorni,valida_dal,valida_al,created_by)
                       VALUES (%s,%s,%s,'ATTIVO',%s,%s,%s,%s,%s,NULL,%s) RETURNING id""",
                    (pk, cliente_pk, numero + 1, nuova, data_fine, orario, finestra, now, ACTOR))
        new_vpk = cur.fetchone()[0]
        for old_id, pos, var_id, _, qty, uom, tipo, iv, _ in righe:
            cur.execute("""INSERT INTO tpo.righe_programma_fornitura
                             (programma_versione_id,posizione,varieta_id,quantita,unita_misura,tipo_ricorrenza,
                              intervallo_giorni)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""", (new_vpk, pos, var_id, qty, uom, tipo, iv))
        cur.execute("""INSERT INTO tpo.audit_eventi
                         (occurred_at,actor,entity_type,entity_public_id,operation,reason,before_data,after_data,
                          correlation_id,provenance)
                       VALUES (%s,%s,'PROGRAMMA_FORNITURA',%s,'UPDATE',%s,%s::jsonb,%s::jsonb,%s,%s)""",
                    (now, ACTOR, public_id, f"Spostamento del giorno di consegna: {motivo}",
                     json.dumps({"numero_versione": numero, "data_inizio": data_inizio.isoformat(),
                                 "giorno": GIORNI[data_inizio.weekday()]}),
                     json.dumps({"numero_versione": numero + 1, "data_inizio": nuova.isoformat(),
                                 "giorno": GIORNI[nuova.weekday()],
                                 "prossime_consegne": [d.isoformat() for d in dopo]}),
                     correlation, PROVENANCE))
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        conn.commit()
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: {public_id} v{numero + 1} ATTIVA con ancora {_giorno(nuova)}; v{numero} chiusa. "
        "Il prossimo ordine lo genera lo scheduler.")
    out("\n== COMANDO CORRETTIVO (torna all'ancora precedente, nuova versione):")
    out(f"   .venv/bin/python {SELF} {public_id} --nuova-ancora {data_inizio.isoformat()} "
        f"--motivo \"Ripristino del giorno precedente\" --esegui")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("programma", help="es. PF-000008")
    ap.add_argument("--nuova-ancora", required=True, help="AAAA-MM-GG: un giorno della settimana nuovo da cui contare")
    ap.add_argument("--motivo", required=True)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, a.programma, date.fromisoformat(a.nuova_ancora), a.motivo, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
