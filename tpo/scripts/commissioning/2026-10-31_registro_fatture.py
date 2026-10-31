"""REGISTRO FATTURE ESTERNE (31/10/2026): porta in TPO le fatture gia' emesse fuori dal sistema (TP-2026-NNN).

  .venv/bin/python scripts/commissioning/2026-10-31_registro_fatture.py                      # anteprima (non scrive)
  .venv/bin/python scripts/commissioning/2026-10-31_registro_fatture.py --esegui             # registra davvero
  .venv/bin/python scripts/commissioning/2026-10-31_registro_fatture.py --collega TP-2026-027 CON-000006 CON-000019 [--data AAAA-MM-GG] --esegui
  .venv/bin/python scripts/commissioning/2026-10-31_registro_fatture.py --stato [--mese 2026-10]   # solo lettura: chi e' da fatturare

Legge due file in outputs/fatture_esterne/ (NON in git: contengono NIF/CIF e indirizzi):
  registro_fatture_2026.csv   numero;data;cliente;cliente_pid;imponibile;igic;totale;tipo;stato;rettifica_di;consegne;
                              anomalia;note;fonte        (consegne = codici CON separati da spazio, solo se SICURE)
  clienti_fiscali.csv         cliente_pid;ragione_sociale;cif_nif;indirizzo;note
Cambia i file con --registro / --fiscali. Il numero e' quello scritto sul PDF e puo' ripetersi (duplicati storici 005, 006,
008): vengono registrati cosi' come sono e segnalati, non corretti. Una riga e' gia' registrata se coincidono numero + data +
cliente: rilanciare non duplica nulla. L'anteprima controlla: totale = imponibile + IGIC, consegne esistenti e CONSEGNATE, del
cliente giusto, non gia' fatturate, e valore al listino uguale all'imponibile; poi i buchi e i duplicati di numerazione.
Con --esegui scrive tutto in UNA transazione (+ audit FATTURA_ESTERNA). Non emette fatture e non tocca tpo.fatture.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

TIMEZONE = ZoneInfo("Atlantic/Canary")
ACTOR = "matteo"
CENT = Decimal("0.01")
DIR = ROOT / "outputs" / "fatture_esterne"
NUM_RE = re.compile(r"^TP-(\d{4})-(\d{3,})$")


class Stop(Exception):
    pass


def _dec(txt: str, nome: str) -> Decimal | None:
    txt = (txt or "").strip().replace(",", ".")
    if not txt:
        return None
    try:
        return Decimal(txt).quantize(CENT)
    except InvalidOperation:
        raise Stop(f"{nome}: '{txt}' non e' un numero.")


def leggi_registro(path: Path) -> list[dict]:
    if not path.exists():
        raise Stop(f"file non trovato: {path}")
    righe = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for n, r in enumerate(csv.DictReader(fh, delimiter=";"), start=2):
            try:
                giorno = date.fromisoformat(r["data"].strip())
            except ValueError:
                raise Stop(f"{path.name} riga {n}: data '{r['data']}' non valida (AAAA-MM-GG).")
            imp, igic, tot = _dec(r["imponibile"], f"riga {n} imponibile"), _dec(r["igic"], f"riga {n} igic"), \
                _dec(r["totale"], f"riga {n} totale")
            if tot is None:
                raise Stop(f"riga {n} ({r['numero']}): totale mancante.")
            if (imp is None) != (igic is None):
                raise Stop(f"riga {n} ({r['numero']}): imponibile e IGIC vanno indicati insieme o lasciati vuoti.")
            if imp is not None and imp + igic != tot:
                raise Stop(f"riga {n} ({r['numero']}): imponibile + IGIC ({imp + igic}) diverso dal totale ({tot}).")
            righe.append({
                "numero": r["numero"].strip(), "data": giorno, "cliente": r["cliente"].strip(),
                "cliente_pid": r["cliente_pid"].strip() or None, "imponibile": imp, "igic": igic, "totale": tot,
                "tipo": r["tipo"].strip() or "FATTURA", "stato": r["stato"].strip() or "EMESSA",
                "rettifica_di": r["rettifica_di"].strip() or None, "consegne": r["consegne"].split(),
                "anomalia": r["anomalia"].strip() or None, "note": r["note"].strip() or None,
                "fonte": r["fonte"].strip() or None,
            })
    return righe


def leggi_fiscali(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [{"cliente_pid": r["cliente_pid"].strip(), "ragione_sociale": r["ragione_sociale"].strip(),
                 "cif_nif": r["cif_nif"].strip() or None, "indirizzo": r["indirizzo"].strip() or None,
                 "note": r["note"].strip() or None,
                 "prezzo_set": _dec(r.get("prezzo_set") or "", f"prezzo_set {r['cliente_pid']}")} for r in csv.DictReader(fh, delimiter=";")]


def _euro(v: Decimal) -> str:
    return f"{v.quantize(CENT, rounding=ROUND_HALF_UP):.2f} EUR"


def _audit(cur, entity_pid, operation, reason, after, corr):
    cur.execute(
        """INSERT INTO tpo.audit_eventi (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                                         before_data,after_data,correlation_id,provenance)
           VALUES (CURRENT_TIMESTAMP,%s,'FATTURA_ESTERNA',%s,%s,%s,NULL,%s::jsonb,%s,%s)""",
        (ACTOR, entity_pid, operation, reason, json.dumps(after), corr,
         json.dumps({"registro_fatture_esterne": "OWNER_AUTHORIZED"})))


def _clienti(cur):
    cur.execute("SELECT public_id, id, denominazione FROM tpo.clienti")
    return {p: (i, n) for p, i, n in cur.fetchall()}


def _consegna(cur, codice):
    cur.execute("""SELECT c.id, c.stato::text, cl.public_id, c.data_effettiva,
                          (SELECT fe.numero FROM tpo.fatture_esterne_consegne x JOIN tpo.fatture_esterne fe ON fe.id=x.fattura_esterna_id
                            WHERE x.consegna_id=c.id AND fe.tipo='FATTURA' AND fe.stato='EMESSA' LIMIT 1),
                          EXISTS (SELECT 1 FROM tpo.fatture_consegne fc WHERE fc.consegna_id=c.id)
                   FROM tpo.consegne c JOIN tpo.clienti cl ON cl.id=c.cliente_id WHERE c.public_id=%s""", (codice,))
    return cur.fetchone()


def _valore(cur, consegna_pk) -> Decimal | None:
    cur.execute("""SELECT rc.quantita, l.prezzo_unitario, rc.unita_misura::text FROM tpo.righe_consegna rc
                   LEFT JOIN tpo.listino_varieta l ON l.varieta_id=rc.varieta_id WHERE rc.consegna_id=%s""", (consegna_pk,))
    tot = Decimal(0)
    for q, p, u in cur.fetchall():
        if p is None or u != "SET":
            return None
        tot += Decimal(q) * Decimal(p)
    return tot


def numerazione(righe, out):
    """Buchi e duplicati sui numeri TP-AAAA-NNN (solo FATTURA); le rettificative hanno una serie propria."""
    per_anno = defaultdict(lambda: defaultdict(list))
    for r in righe:
        m = NUM_RE.match(r["numero"])
        if r["tipo"] == "FATTURA" and m:
            per_anno[m.group(1)][int(m.group(2))].append(r)
    for anno, numeri in sorted(per_anno.items()):
        dup = {n: v for n, v in numeri.items() if len(v) > 1}
        buchi = [n for n in range(1, max(numeri) + 1) if n not in numeri]
        out(f"\nNumerazione {anno}: da {min(numeri):03d} a {max(numeri):03d}, {len(numeri)} numeri usati.")
        for n, v in sorted(dup.items()):
            out(f"   DUPLICATO TP-{anno}-{n:03d}: " + " / ".join(f"{x['data'].isoformat()} {x['cliente']} {_euro(x['totale'])}" for x in v))
        if buchi:
            out("   Numeri non presenti (mai emessi o non ancora ritrovati): " + ", ".join(f"{n:03d}" for n in buchi))


def run(conn, registro, fiscali, esegui, out=print) -> int:
    cur = conn.cursor()
    clienti = _clienti(cur)
    cur.execute("SELECT numero, data_emissione, cliente_nome FROM tpo.fatture_esterne")
    presenti = {(n, d, c) for n, d, c in cur.fetchall()}
    out(f"== REGISTRO FATTURE ESTERNE " + ("(ESECUZIONE)" if esegui else "(ANTEPRIMA: nulla viene scritto)"))
    da_inserire, problemi, collegati, gia = [], [], set(), 0
    for r in registro:
        chiave = (r["numero"], r["data"], r["cliente"])
        if r["cliente_pid"] and r["cliente_pid"] not in clienti:
            problemi.append(f"{r['numero']}: cliente {r['cliente_pid']} inesistente in TPO.")
            continue
        if chiave in presenti:
            gia += 1
            continue
        note_riga = []
        for codice in r["consegne"]:
            info = _consegna(cur, codice)
            if info is None:
                problemi.append(f"{r['numero']}: {codice} non esiste.")
            elif info[1] != "CONSEGNATA":
                problemi.append(f"{r['numero']}: {codice} non e' CONSEGNATA ({info[1]}).")
            elif r["cliente_pid"] and info[2] != r["cliente_pid"]:
                problemi.append(f"{r['numero']}: {codice} e' di {info[2]}, la fattura e' per {r['cliente_pid']}.")
            elif info[4] or info[5] or codice in collegati:
                dove = info[4] or ("una fattura emessa da TPO" if info[5] else "un'altra riga di questo file")
                problemi.append(f"{r['numero']}: {codice} risulta gia' fatturata ({dove}).")
            else:
                collegati.add(codice)
        if r["consegne"] and not any(p.startswith(r["numero"]) for p in problemi):
            valori = [_valore(cur, _consegna(cur, c)[0]) for c in r["consegne"]]
            if None not in valori and r["imponibile"] is not None and sum(valori) != r["imponibile"]:
                problemi.append(f"{r['numero']}: le consegne valgono {_euro(sum(valori))} al listino, la fattura ha imponibile {_euro(r['imponibile'])}.")
        if r["stato"] == "ANNULLATA" and r["consegne"]:
            problemi.append(f"{r['numero']}: una fattura ANNULLATA non si collega a consegne.")
        da_inserire.append(r)
    nuovi = len(da_inserire)
    out(f"\nFatture nel file: {len(registro)}; gia' registrate: {gia}; da registrare ora: {nuovi}")
    for r in da_inserire:
        flag = f"  [{r['anomalia']}]" if r["anomalia"] else ""
        out(f"   {r['numero']:<12} {r['data'].isoformat()} {r['cliente']:<28} {_euro(r['totale']):>12} {r['tipo'][:4]}.{r['stato'][:4]}"
            + (f"  consegne: {' '.join(r['consegne'])}" if r["consegne"] else "") + flag)
    # dati fiscali
    cur.execute("SELECT c.public_id FROM tpo.dati_fiscali_cliente d JOIN tpo.clienti c ON c.id=d.cliente_id")
    gia_fiscali = {p for (p,) in cur.fetchall()}
    for f in fiscali:
        if f["cliente_pid"] not in clienti:
            problemi.append(f"dati fiscali: cliente {f['cliente_pid']} inesistente.")
    out(f"\nDati fiscali clienti: {len(fiscali)} nel file ({sum(1 for f in fiscali if f['cliente_pid'] in gia_fiscali)} gia' presenti, aggiornati).")
    tutte = [dict(r) for r in registro]
    numerazione(tutte, out)
    if problemi:
        out("\nSTOP, da risolvere prima di registrare:")
        for p in problemi:
            out("   - " + p)
        return 1
    if not esegui:
        out("\nTutto coerente. Per registrare: stesso comando con --esegui.")
        return 0
    corr = "registro-fatture-esterne-2026-10-31"
    motivo = "Registro delle fatture gia' emesse fuori da TPO (TP-2026-NNN), richiesta di Matteo il 31/10/2026"
    for r in da_inserire:
        cid = clienti[r["cliente_pid"]][0] if r["cliente_pid"] else None
        cur.execute("""INSERT INTO tpo.fatture_esterne (numero,data_emissione,cliente_id,cliente_nome,imponibile,igic,totale,
                         tipo,stato,rettifica_di,anomalia,note,fonte,created_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (r["numero"], r["data"], cid, r["cliente"], r["imponibile"], r["igic"], r["totale"], r["tipo"],
                     r["stato"], r["rettifica_di"], r["anomalia"], r["note"], r["fonte"], ACTOR))
        fid = cur.fetchone()[0]
        for codice in r["consegne"]:
            cur.execute("INSERT INTO tpo.fatture_esterne_consegne (fattura_esterna_id,consegna_id,created_by) "
                        "VALUES (%s,(SELECT id FROM tpo.consegne WHERE public_id=%s),%s)", (fid, codice, ACTOR))
        _audit(cur, r["numero"], "INSERT", motivo,
               {"data": r["data"].isoformat(), "cliente": r["cliente"], "totale": str(r["totale"]), "tipo": r["tipo"],
                "stato": r["stato"], "consegne": r["consegne"], "anomalia": r["anomalia"]}, f"{corr}-{r['numero']}-{r['data']}")
    for f in fiscali:
        cid = clienti[f["cliente_pid"]][0]
        cur.execute("""INSERT INTO tpo.dati_fiscali_cliente (cliente_id,ragione_sociale,cif_nif,indirizzo,note,prezzo_set_fattura,updated_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (cliente_id) DO UPDATE SET ragione_sociale=EXCLUDED.ragione_sociale,
                         cif_nif=EXCLUDED.cif_nif, indirizzo=EXCLUDED.indirizzo, note=EXCLUDED.note,
                         prezzo_set_fattura=EXCLUDED.prezzo_set_fattura, updated_at=now(), updated_by=EXCLUDED.updated_by""",
                    (cid, f["ragione_sociale"], f["cif_nif"], f["indirizzo"], f["note"], f["prezzo_set"], ACTOR))
        _audit(cur, f["cliente_pid"], "UPDATE" if f["cliente_pid"] in gia_fiscali else "INSERT",
               "Dati fiscali cliente (da fatture gia' emesse), richiesta di Matteo il 31/10/2026",
               {"ragione_sociale": f["ragione_sociale"], "cif_nif": f["cif_nif"], "prezzo_set": None if f["prezzo_set"] is None else str(f["prezzo_set"])}, f"{corr}-fiscali-{f['cliente_pid']}")
    conn.commit()
    out(f"\nFATTO: {nuovi} fatture registrate, {len(fiscali)} anagrafiche fiscali, tutto in una transazione.")
    return 0


def collega(conn, numero, codici, giorno, esegui, cliente_pid=None, out=print) -> int:
    cur = conn.cursor()
    cur.execute("""SELECT id, data_emissione, cliente_id, cliente_nome, stato, imponibile, totale FROM tpo.fatture_esterne
                   WHERE numero=%s AND (%s::date IS NULL OR data_emissione=%s) ORDER BY data_emissione""", (numero, giorno, giorno))
    trovate = cur.fetchall()
    if not trovate:
        out(f"STOP: fattura {numero} non registrata."); return 2
    if len(trovate) > 1:
        out(f"STOP: {numero} esiste {len(trovate)} volte (duplicato storico): aggiungi --data AAAA-MM-GG tra "
            + ", ".join(str(t[1]) for t in trovate)); return 2
    fid, data, cli_id, nome, stato, imp, tot = trovate[0]
    if stato != "EMESSA":
        out(f"STOP: {numero} e' {stato}: non si collega a consegne."); return 2
    assegna = None
    if cliente_pid:
        cl = _clienti(cur).get(cliente_pid)
        if cl is None:
            out(f"STOP: cliente {cliente_pid} inesistente."); return 2
        if cli_id is not None and cli_id != cl[0]:
            out(f"STOP: {numero} e' gia' del cliente {nome}: non si cambia."); return 2
        if cli_id is None:
            assegna, cli_id = cl, cl[0]
    valore, problemi = Decimal(0), []
    for c in codici:
        info = _consegna(cur, c)
        if info is None: problemi.append(f"{c} non esiste")
        elif info[1] != "CONSEGNATA": problemi.append(f"{c} non e' CONSEGNATA")
        elif info[4] or info[5]: problemi.append(f"{c} gia' fatturata")
        else:
            cur.execute("SELECT 1 FROM tpo.consegne c JOIN tpo.clienti cl ON cl.id=c.cliente_id WHERE c.public_id=%s AND cl.id=%s", (c, cli_id))
            if cli_id and not cur.fetchone(): problemi.append(f"{c} e' di un altro cliente")
            v = _valore(cur, info[0])
            valore = None if (v is None or valore is None) else valore + v
    out(f"== COLLEGA {numero} ({data}, {nome}, totale {_euro(tot)}) a: {' '.join(codici)}"
        + (f"\n   la fattura viene assegnata al cliente {cliente_pid} ({assegna[1]})" if assegna else ""))
    if valore is not None:
        out(f"   valore al listino delle consegne: {_euro(valore)}" + ("  <- NON coincide con l'imponibile" if imp is not None and valore != imp else ""))
    if problemi:
        out("STOP: " + "; ".join(problemi)); return 1
    if not esegui:
        out("Anteprima: aggiungi --esegui per collegare."); return 0
    for c in codici:
        cur.execute("INSERT INTO tpo.fatture_esterne_consegne (fattura_esterna_id,consegna_id,created_by) "
                    "VALUES (%s,(SELECT id FROM tpo.consegne WHERE public_id=%s),%s)", (fid, c, ACTOR))
    if assegna:
        cur.execute("UPDATE tpo.fatture_esterne SET cliente_id=%s, anomalia=%s WHERE id=%s",
                    (assegna[0], "IGIC da verificare; cliente confermato da Matteo il 31/10/2026", fid))
    _audit(cur, numero, "CORRECTION", "Collegamento fattura-consegne confermato da Matteo il 31/10/2026",
           {"data": data.isoformat(), "consegne": codici, "cliente": cliente_pid}, f"collega-fattura-esterna-{numero}-{data}")
    conn.commit()
    out("FATTO."); return 0


def correggi(conn, numero, giorno, nuovo, esegui, out=print) -> int:
    """Corregge una riga NON verificata (fonte 'registro del 31/10 compilato da ChatGPT') con i dati del documento."""
    cur = conn.cursor()
    cur.execute("""SELECT id, numero, data_emissione, cliente_nome, imponibile, igic, totale, stato, fonte FROM tpo.fatture_esterne
                   WHERE numero=%s AND (%s::date IS NULL OR data_emissione=%s) ORDER BY data_emissione""", (numero, giorno, giorno))
    trov = cur.fetchall()
    if len(trov) != 1:
        out(f"STOP: {numero}: trovate {len(trov)} righe" + (" (usa --data per scegliere)." if trov else ".")); return 2
    fid, num, data, cliente, imp, igic, tot, stato, fonte = trov[0]
    if not (fonte or "").startswith("registro del 31/10 compilato da ChatGPT"):
        out(f"STOP: {numero} e' gia' verificata (fonte: {fonte}): non si corregge."); return 2
    if not nuovo.get("fonte"):
        out("STOP: indica --fonte con il documento che verifica la riga (es. \"PDF TP-2026-007 inviato da Matteo il 31/10\")."); return 2
    n_imp = nuovo["imponibile"] if nuovo.get("imponibile") is not None else imp
    n_igic = nuovo["igic"] if nuovo.get("igic") is not None else igic
    n_tot = nuovo["totale"] if nuovo.get("totale") is not None else (n_imp + n_igic if n_imp is not None and n_igic is not None else tot)
    if (n_imp is None) != (n_igic is None) or (n_imp is not None and n_imp + n_igic != n_tot):
        out(f"STOP: imponibile + IGIC ({n_imp} + {n_igic}) diverso dal totale ({n_tot})."); return 2
    nuovi = {"numero": nuovo.get("numero") or num, "data_emissione": nuovo.get("data") or data,
             "cliente_nome": nuovo.get("cliente_nome") or cliente, "imponibile": n_imp, "igic": n_igic, "totale": n_tot,
             "stato": nuovo.get("stato") or stato, "fonte": nuovo["fonte"]}
    prima = {"numero": num, "data_emissione": data, "cliente_nome": cliente, "imponibile": imp, "igic": igic, "totale": tot,
             "stato": stato, "fonte": fonte}
    out(f"== CORREGGI {num} ({data}, {cliente})")
    for k in nuovi:
        flag = "" if nuovi[k] == prima[k] else "   <- CAMBIA"
        out(f"   {k:<14} {str(prima[k]):<45} -> {nuovi[k]}{flag}")
    if not esegui:
        out("Anteprima: aggiungi --esegui."); return 0
    cur.execute("""UPDATE tpo.fatture_esterne SET numero=%s, data_emissione=%s, cliente_nome=%s, imponibile=%s, igic=%s, totale=%s,
                     stato=%s, fonte=%s WHERE id=%s""",
                (nuovi["numero"], nuovi["data_emissione"], nuovi["cliente_nome"], nuovi["imponibile"], nuovi["igic"], nuovi["totale"],
                 nuovi["stato"], nuovi["fonte"], fid))
    cur.execute("""INSERT INTO tpo.audit_eventi (occurred_at,actor,entity_type,entity_public_id,operation,reason,before_data,after_data,
                     correlation_id,provenance) VALUES (CURRENT_TIMESTAMP,%s,'FATTURA_ESTERNA',%s,'CORRECTION',%s,%s::jsonb,%s::jsonb,%s,%s)""",
                (ACTOR, nuovi["numero"], "Riga del registro verificata sul documento da Matteo il 31/10/2026",
                 json.dumps({k: str(v) for k, v in prima.items()}), json.dumps({k: str(v) for k, v in nuovi.items()}),
                 f"correggi-fattura-esterna-{num}-{fid}", json.dumps({"registro_fatture_esterne": "OWNER_AUTHORIZED"})))
    conn.commit()
    out("FATTO."); return 0


def stato(conn, mese, out=print) -> int:
    cur = conn.cursor()
    cur.execute("""SELECT cl.denominazione, c.public_id, c.data_effettiva FROM tpo.consegne c JOIN tpo.clienti cl ON cl.id=c.cliente_id
                   WHERE c.stato='CONSEGNATA' AND NOT EXISTS (SELECT 1 FROM tpo.fatture_esterne_consegne x JOIN tpo.fatture_esterne fe ON fe.id=x.fattura_esterna_id
                                              WHERE x.consegna_id=c.id AND fe.tipo='FATTURA' AND fe.stato='EMESSA')
                     AND NOT EXISTS (SELECT 1 FROM tpo.fatture_consegne f WHERE f.consegna_id=c.id)
                   ORDER BY cl.denominazione, c.data_effettiva""")
    per = defaultdict(list)
    for nome, pid, eff in cur.fetchall():
        g = eff.astimezone(TIMEZONE).date()
        if g.strftime("%Y-%m") == mese:
            per[nome].append((pid, g))
    out(f"== CONSEGNE {mese} SENZA FATTURA (SOLA LETTURA)")
    tot = 0
    for nome, lst in sorted(per.items()):
        valori = []
        for pid, g in lst:
            valori.append(_valore(cur, _consegna(cur, pid)[0]))
        v = sum(x for x in valori if x is not None)
        tot += v
        out(f"\n{nome}: {len(lst)} consegne, {_euro(v)} al listino")
        for (pid, g), val in zip(lst, valori):
            out(f"   {pid}  {g.isoformat()}  {'n.d.' if val is None else _euro(val)}")
    out(f"\nTOTALE senza fattura: {_euro(tot)} su {len(per)} clienti")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registro", default=str(DIR / "registro_fatture_2026.csv"))
    ap.add_argument("--fiscali", default=str(DIR / "clienti_fiscali.csv"))
    ap.add_argument("--collega", nargs="+", metavar=("NUMERO", "CON"), help="NUMERO CON-... CON-...")
    ap.add_argument("--cliente", help="con --collega: assegna la fattura a questo cliente (CLI-...) se non ne ha uno")
    ap.add_argument("--data", help="AAAA-MM-GG, per distinguere un numero duplicato")
    ap.add_argument("--correggi", metavar="NUMERO", help="corregge una riga NON verificata con i dati del documento (serve --fonte)")
    ap.add_argument("--fonte", help="con --correggi: il documento che verifica la riga")
    ap.add_argument("--imponibile"); ap.add_argument("--igic"); ap.add_argument("--totale")
    ap.add_argument("--cliente-nome", dest="cliente_nome"); ap.add_argument("--nuovo-numero"); ap.add_argument("--nuova-data")
    ap.add_argument("--nuovo-stato", choices=["EMESSA", "ANNULLATA"])
    ap.add_argument("--stato", action="store_true", help="solo lettura: consegne del mese senza fattura")
    ap.add_argument("--mese", default="2026-10")
    ap.add_argument("--esegui", action="store_true")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        if a.collega:
            if len(a.collega) < 2:
                print("STOP: --collega NUMERO CON-... [CON-...]"); return 2
            return collega(conn, a.collega[0], a.collega[1:], date.fromisoformat(a.data) if a.data else None, a.esegui, a.cliente)
        if a.correggi:
            nuovo = {"fonte": a.fonte, "imponibile": _dec(a.imponibile, "--imponibile"), "igic": _dec(a.igic, "--igic"),
                     "totale": _dec(a.totale, "--totale"), "cliente_nome": a.cliente_nome, "numero": a.nuovo_numero,
                     "data": date.fromisoformat(a.nuova_data) if a.nuova_data else None, "stato": a.nuovo_stato}
            return correggi(conn, a.correggi, date.fromisoformat(a.data) if a.data else None, nuovo, a.esegui)
        if a.stato:
            return stato(conn, a.mese)
        return run(conn, leggi_registro(Path(a.registro)), leggi_fiscali(Path(a.fiscali)), a.esegui)
    except Stop as exc:
        print(f"STOP: {exc}"); return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
