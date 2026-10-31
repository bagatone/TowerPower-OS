"""GENERA FATTURE (31/10/2026): prepara le fatture TP-2026-NNN mancanti, le registra in TPO e scrive i PDF.

  .venv/bin/python scripts/commissioning/2026-10-31_genera_fatture.py --escludi "Alchimia,Oca Bianca,Splash"      # anteprima
  .venv/bin/python scripts/commissioning/2026-10-31_genera_fatture.py --escludi "..." --data-emissione 2026-10-31 --esegui
  .venv/bin/python scripts/commissioning/2026-10-31_genera_fatture.py --rigenera TP-2026-038 [--data AAAA-MM-GG]   # rifà il PDF (es. dopo un pagamento)

Prende le consegne CONSEGNATE del mese (default 2026-10) che NON sono in nessuna fattura (ne' TPO ne' registro delle fatture
esterne) e, per ogni cliente che ha i DATI FISCALI registrati, prepara le fatture:
  - clienti "una fattura per consegna" (default: Okra, Puipana, Splash, Tsunami; cambia con --per-consegna "..."): una fattura per consegna;
  - tutti gli altri: UNA fattura mensile con tutte le consegne;
  - --unisci CLI-000014=CLI-000004: le consegne di un'anagrafica doppia finiscono nella fattura dell'altra (default: il doppione di Salvaje).
I clienti senza dati fiscali vengono saltati e segnalati. --escludi salta clienti per nome (anche una parte).
Numeri: dal successivo all'ultimo TP-AAAA-NNN del registro. Importi: quantita' x prezzo di listino (IGIC dal listino).
Pagamenti gia' registrati (per consegna) compaiono sul PDF come "Pago ..." e "SALDO PENDIENTE".
I PDF vanno in ~/Desktop/fatture towerpower/ (cambia con --cartella). Emittente e IBAN da config/fattura_emittente.yaml (non in git).
Con --esegui: registra nel registro fatture esterne (UNA transazione, audit) e poi scrive i PDF; se un PDF non si scrive la
fattura resta registrata e basta --rigenera. Rilanciare non crea duplicati (le consegne sono gia' collegate).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

TIMEZONE = ZoneInfo("Atlantic/Canary")
ACTOR = "matteo"
CENT = Decimal("0.01")
EMITTENTE_FILE = ROOT / "config" / "fattura_emittente.yaml"
CARTELLA = Path.home() / "Desktop" / "fatture towerpower"
PER_CONSEGNA_DEFAULT = "Okra,Puipana,Splash,Tsunami"
UNISCI_DEFAULT = "CLI-000014=CLI-000004"
NUM_RE = re.compile(r"^TP-(\d{4})-(\d{3,})$")
MESI = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
SPAGNOLO = {"Basilico": "Albahaca", "Girasole": "Girasol", "Rucola": "Rúcula"}
METODO = {"BONIFICO": "transferencia", "CONTANTI": "efectivo", "CARTA": "tarjeta", "BIZUM": "Bizum", "ALTRO": "otro"}


class Stop(Exception):
    pass


def _fold(t): return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
def _n(v): t = format(Decimal(v).normalize(), "f"); return (t.rstrip("0").rstrip(".") if "." in t else t).replace(".", ",") or "0"
def _eur(v): return f"{Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP):.2f}".replace(".", ",") + " EUR"
def _q(v): return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)
def _dmy(d): return d.strftime("%d/%m/%Y")


SQL_DA_FATTURARE = """
SELECT c.id, c.public_id, c.data_effettiva, cl.id, cl.public_id, cl.denominazione
FROM tpo.consegne c JOIN tpo.clienti cl ON cl.id = c.cliente_id
WHERE c.stato = 'CONSEGNATA'
  AND NOT EXISTS (SELECT 1 FROM tpo.fatture_consegne f WHERE f.consegna_id = c.id)
  AND NOT EXISTS (SELECT 1 FROM tpo.fatture_esterne_consegne x JOIN tpo.fatture_esterne fe ON fe.id = x.fattura_esterna_id
                  WHERE x.consegna_id = c.id AND fe.tipo = 'FATTURA' AND fe.stato = 'EMESSA')
ORDER BY cl.denominazione, c.data_effettiva, c.public_id"""
SQL_RIGHE = """
SELECT rc.id, rc.consegna_id, v.denominazione, rc.quantita, rc.unita_misura::text, l.prezzo_unitario, l.aliquota_igic
FROM tpo.righe_consegna rc JOIN tpo.varieta v ON v.id = rc.varieta_id
LEFT JOIN tpo.listino_varieta l ON l.varieta_id = rc.varieta_id
WHERE rc.consegna_id = ANY(%s) ORDER BY rc.consegna_id, rc.posizione"""
SQL_ORIGINI = """
SELECT rc.id, s.codice_tracciabilita, r.public_id
FROM tpo.righe_consegna rc
JOIN tpo.movimenti_magazzino ms ON ms.riga_consegna_id = rc.id AND ms.tipo = 'SCARICO'
JOIN tpo.consumi_lotto cl ON cl.movimento_scarico_id = ms.id AND cl.tipo_consumo = 'CONSEGNA'
JOIN tpo.movimenti_magazzino mc ON mc.id = cl.movimento_carico_id
JOIN tpo.raccolte r ON r.id = mc.raccolta_id JOIN tpo.semine s ON s.id = r.semina_id
WHERE rc.consegna_id = ANY(%s) AND s.codice_tracciabilita IS NOT NULL
ORDER BY rc.id, mc.data_movimento, mc.id"""
SQL_PAGAMENTI = """
SELECT p.consegna_id, p.data_pagamento, p.metodo::text, p.importo FROM tpo.pagamenti_consegna p
WHERE p.consegna_id = ANY(%s) AND p.tipo = 'PAGAMENTO'
  AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna a WHERE a.annulla_pagamento_id = p.id)"""
SQL_FISCALI = """SELECT d.cliente_id, d.ragione_sociale, d.cif_nif, d.indirizzo, d.prezzo_set_fattura FROM tpo.dati_fiscali_cliente d"""


def carica_consegne(cur, pks):
    """{consegna_pk: dict(righe=[...], pagamenti=[...])} con importi di listino."""
    cur.execute(SQL_RIGHE, (pks,))
    righe_pk, righe = [], defaultdict(list)
    for rid, cpk, var, qty, uom, prezzo, aliq in cur.fetchall():
        righe[cpk].append({"rid": rid, "varieta": SPAGNOLO.get(var, var), "qty": Decimal(qty), "uom": uom,
                           "prezzo": None if prezzo is None else Decimal(prezzo),
                           "igic": None if aliq is None else Decimal(aliq), "origini": []})
        righe_pk.append(rid)
    cur.execute(SQL_ORIGINI, (pks,))
    per_riga = {r["rid"]: r for lst in righe.values() for r in lst}
    for rid, codice, rac in cur.fetchall():
        per_riga[rid]["origini"].append((codice, rac))
    cur.execute(SQL_PAGAMENTI, (pks,))
    pagamenti = defaultdict(list)
    for cpk, giorno, metodo, importo in cur.fetchall():
        pagamenti[cpk].append((giorno, metodo, None if importo is None else Decimal(importo)))
    return righe, pagamenti


def importo_riga(r):
    return _q(r["qty"] * r["prezzo"])


def totali(consegne):
    base = igic = Decimal(0)
    for c in consegne:
        for r in c["righe"]:
            imp = importo_riga(r)
            base += imp
            igic += _q(imp * r["igic"] / Decimal(100))
    return _q(base), _q(igic)


def costruisci(cur, mese, escludi, per_consegna, unisci, salta_consegne=()):
    """Fatture da preparare (senza numero) e clienti saltati: ([...], [(nome, motivo)])."""
    cur.execute(SQL_DA_FATTURARE)
    rows = [r for r in cur.fetchall() if r[2].astimezone(TIMEZONE).strftime("%Y-%m") == mese and r[1] not in salta_consegne]
    cur.execute("SELECT public_id, id, denominazione FROM tpo.clienti")
    clienti = {p: (i, n) for p, i, n in cur.fetchall()}
    cur.execute(SQL_FISCALI)
    fiscali = {cid: (rs, cif, ind, None if pz is None else Decimal(pz)) for cid, rs, cif, ind, pz in cur.fetchall()}
    righe, pagamenti = carica_consegne(cur, [r[0] for r in rows]) if rows else ({}, {})
    per_cliente = defaultdict(list)
    for cpk, cpid, eff, cli_pk, cli_pid, nome in rows:
        target = unisci.get(cli_pid, cli_pid)
        per_cliente[target].append({"pk": cpk, "pid": cpid, "data": eff.astimezone(TIMEZONE).date(),
                                    "righe": righe.get(cpk, []), "pagamenti": pagamenti.get(cpk, []), "origine_cliente": cli_pid})
    fatture, saltati = [], []
    for cli_pid, consegne in sorted(per_cliente.items(), key=lambda kv: clienti[kv[0]][1]):
        cli_pk, nome = clienti[cli_pid]
        if any(_fold(e) in _fold(nome) for e in escludi):
            saltati.append((nome, "escluso da te")); continue
        if cli_pk not in fiscali:
            saltati.append((nome, "mancano i dati fiscali")); continue
        mancanti = sorted({r["varieta"] for c in consegne for r in c["righe"] if r["prezzo"] is None or r["igic"] is None or r["uom"] != "SET"})
        if mancanti:
            saltati.append((nome, "listino/unita' non valido per " + ", ".join(mancanti))); continue
        if any(not c["righe"] for c in consegne):
            saltati.append((nome, "consegna senza righe")); continue
        if fiscali[cli_pk][3] is not None:               # prezzo per SET del cliente (es. supplemento distanza)
            for c in consegne:
                for r in c["righe"]:
                    r["prezzo"] = fiscali[cli_pk][3]
        gruppi = [[c] for c in consegne] if any(_fold(p) in _fold(nome) for p in per_consegna) else [consegne]
        for g in gruppi:
            fatture.append({"cliente_pid": cli_pid, "cliente_pk": cli_pk, "nome": nome, "fiscali": fiscali[cli_pk], "consegne": g})
    return fatture, saltati


def prossimo_numero(cur, anno):
    cur.execute("SELECT numero FROM tpo.fatture_esterne WHERE tipo='FATTURA'")
    mx = 0
    for (n,) in cur.fetchall():
        m = NUM_RE.match(n)
        if m and int(m.group(1)) == anno:
            mx = max(mx, int(m.group(2)))
    return mx + 1


def leggi_emittente():
    import yaml
    if not EMITTENTE_FILE.exists():
        raise Stop(f"manca {EMITTENTE_FILE.relative_to(ROOT)} (copia config/fattura_emittente.example.yaml).")
    d = yaml.safe_load(EMITTENTE_FILE.read_text(encoding="utf-8"))
    return d["emittente"], d["pagamento"], d.get("piede", "")


def _indirizzo_righe(ind):
    """Indirizzo su righe come sulle fatture: via / CAP e localita' / provincia."""
    if not ind:
        return []
    via, _, resto = ind.rpartition(", ")
    righe = [via, resto] if via else [ind]
    if "las palmas" not in ind.lower():
        righe.append("Las Palmas, España")
    return righe


def render_pdf(f, numero, giorno, emittente, pagamento, piede, rettifica=None) -> bytes:
    """rettifica = (numero, data) della fattura annullata: documento RECTIFICATIVA con importi negativi."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    sgn = -1 if rettifica else 1
    titolo_doc = "FACTURA RECTIFICATIVA" if rettifica else "FACTURA"
    verde = colors.HexColor("#1F6B4A")
    grigio = colors.HexColor("#555555")
    st = getSampleStyleSheet()
    base = ParagraphStyle("b", parent=st["Normal"], fontName="Helvetica", fontSize=9, leading=13)
    small = ParagraphStyle("s", parent=base, fontSize=8, leading=10, textColor=grigio)
    strong = ParagraphStyle("st", parent=base, fontName="Helvetica-Bold")
    nome_style = ParagraphStyle("n", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=15)
    titolo = ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=verde)
    th = ParagraphStyle("th", parent=base, fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=colors.white)
    right = ParagraphStyle("r", parent=base, alignment=2)
    rights = ParagraphStyle("rs", parent=strong, alignment=2, fontSize=10, leading=14)
    saldo = ParagraphStyle("sa", parent=rights, textColor=verde)
    p = lambda t, s=base: Paragraph(escape(t), s)
    ragione, cif, ind = f["fiscali"][:3]
    consegne = sorted(f["consegne"], key=lambda c: (c["data"], c["pid"]))
    base_imp, igic = totali(consegne)
    totale = base_imp + igic

    def pagina(canvas, doc):
        w, h = A4
        canvas.saveState()
        canvas.setFillColor(verde)
        canvas.rect(0, h - 24 * mm, w, 24 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 17)
        canvas.drawString(15 * mm, h - 15 * mm, "TOWER POWER")
        canvas.drawRightString(w - 15 * mm, h - 14 * mm, titolo_doc)
        canvas.setStrokeColor(colors.HexColor("#CCCCCC"))
        canvas.setLineWidth(0.5)
        canvas.line(15 * mm, 18 * mm, w - 15 * mm, 18 * mm)
        canvas.setFillColor(grigio)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(15 * mm, 13 * mm, piede)
        canvas.restoreState()

    def sezione(testo):
        t = Table([[p(testo, titolo)]], colWidths=[180 * mm])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#CCCCCC")),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t

    def blocco(righe):
        t = Table([[r] for r in righe], colWidths=[180 * mm])
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        return t

    story = [blocco([p(line, strong if i == 0 else base) for i, line in enumerate(emittente)])]
    story += [Spacer(1, 7 * mm), sezione("CLIENTE"), Spacer(1, 2 * mm)]
    mese = f"{MESI[consegne[0]['data'].month - 1]} de {consegne[0]['data'].year}"
    cliente_blk = [p(f["nome"], nome_style), p(ragione, strong)]
    if cif:
        cliente_blk.append(p(f"CIF: {cif}"))
    cliente_blk += [p(r) for r in _indirizzo_righe(ind)]
    meta_blk = [p(f"Periodo: {mese}"), p(f"Número: {numero}", strong), p(f"Fecha: {_dmy(giorno)}")]
    if rettifica:
        meta_blk += [p(f"Rectifica la factura {rettifica[0]} de {_dmy(rettifica[1])}"), p("Motivo: anulación íntegra de la factura")]
    t = Table([[cliente_blk, meta_blk]], colWidths=[110 * mm, 70 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [t, Spacer(1, 8 * mm)]
    rows = [[p("ENTREGA / ALBARÁN", th), p("VARIEDAD", th), p("SETS", th), p("CÓDIGO DE TRAZABILIDAD", th), p("IMPORTE", ParagraphStyle("thr", parent=th, alignment=2))]]
    for c in consegne:
        first = True
        for r in c["righe"]:
            tr = " / ".join(f"{cod} / {rac}" for cod, rac in r["origini"]) or "origen no trazado"
            rows.append([p(f"{c['data'].strftime('%d/%m')} - {c['pid']}" if first else ""), p(r["varieta"]),
                         p(_n(sgn * r["qty"])), p(tr), p(_eur(sgn * importo_riga(r)), right)])
            first = False
    tab = Table(rows, colWidths=[42 * mm, 32 * mm, 14 * mm, 62 * mm, 30 * mm])
    estilo = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BACKGROUND", (0, 0), (-1, 0), verde),
              ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
              ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#DDDDDD"))]
    for i in range(2, len(rows), 2):
        estilo.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F4F4F4")))
    tab.setStyle(TableStyle(estilo))
    story += [tab, Spacer(1, 4 * mm)]
    sets = sum((r["qty"] for c in consegne for r in c["righe"]), Decimal(0))
    prezzi = {r["prezzo"] for c in consegne for r in c["righe"]}
    izq = [p(f"Cantidad total: {_n(sgn * sets)} sets", strong)]
    if len(prezzi) == 1:
        izq.append(p(f"Precio unitario: {_eur(next(iter(prezzi)))}/set"))
    if igic == 0:
        izq += [Spacer(1, 3 * mm), p("Operación exenta de IGIC.")]
    der = [p(f"Base imponible: {_eur(sgn * base_imp)}", right),
           p("IGIC: exento - 0,00 EUR" if igic == 0 else f"IGIC: {_eur(sgn * igic)}", right),
           Spacer(1, 3 * mm), p(f"TOTAL: {_eur(sgn * totale)}", rights)]
    pagato = Decimal(0)
    pag_lines = defaultdict(Decimal)
    for c in consegne:
        valore_c = sum((importo_riga(r) for r in c["righe"]), Decimal(0))
        for giorno_p, metodo, importo in c["pagamenti"]:
            imp = importo if importo is not None else valore_c
            pag_lines[(giorno_p, metodo)] += imp
            pagato += imp
    for (g, m), imp in ([] if rettifica else sorted(pag_lines.items())):
        quale = "Pago recibido" if m == "ALTRO" else f"Pago en {METODO.get(m, m.lower())}"
        der.append(p(f"{quale} ({_dmy(g)}): {_eur(imp)}", right))
    if not rettifica:
        der.append(p(f"SALDO PENDIENTE: {_eur(max(totale - pagato, Decimal(0)))}", saldo))
    tt = Table([[izq, der]], colWidths=[85 * mm, 95 * mm])
    tt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [tt]
    if not rettifica:
        story += [Spacer(1, 9 * mm), sezione("PAGO POR TRANSFERENCIA BANCARIA"), Spacer(1, 2 * mm), blocco([p(line) for line in pagamento])]
    buf = BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=34 * mm, bottomMargin=24 * mm,
                      title=f"{titolo_doc.title()} {numero}", author="Tower Power").build(story, onFirstPage=pagina, onLaterPages=pagina)
    return buf.getvalue()


def nome_file(numero, nome, giorno):
    pulito = re.sub(r"[^A-Za-z0-9]+", "_", unicodedata.normalize("NFD", nome).encode("ascii", "ignore").decode()).strip("_").upper()
    return f"{numero}_{pulito}_{giorno.isoformat()}.pdf"


def run(conn, mese, escludi, per_consegna, unisci, giorno, cartella, esegui, salta_consegne=(), out=print) -> int:
    cur = conn.cursor()
    fatture, saltati = costruisci(cur, mese, escludi, per_consegna, unisci, salta_consegne)
    if not fatture:
        out("Nessuna fattura da preparare."); [out(f"   saltato {n}: {m}") for n, m in saltati]; return 0
    cur.execute("LOCK TABLE tpo.fatture_esterne IN SHARE ROW EXCLUSIVE MODE")
    prossimo = prossimo_numero(cur, giorno.year)
    emittente, pagamento, piede = leggi_emittente()
    out(f"== GENERA FATTURE {mese}, data {giorno.isoformat()} " + ("(ESECUZIONE)" if esegui else "(ANTEPRIMA: nulla viene scritto)"))
    tot = Decimal(0)
    for i, f in enumerate(fatture):
        f["numero"] = f"TP-{giorno.year}-{prossimo + i:03d}"
        base_imp, igic = totali(f["consegne"])
        f["base"], f["igic"] = base_imp, igic
        pagato = sum((imp if imp is not None else sum((importo_riga(r) for r in c["righe"]), Decimal(0)))
                     for c in f["consegne"] for _g, _m, imp in c["pagamenti"]) if any(c["pagamenti"] for c in f["consegne"]) else Decimal(0)
        tot += base_imp + igic
        out(f"\n{f['numero']}  {f['nome']}  ->  {f['fiscali'][0]} ({f['fiscali'][1]})"
            + (f"  [prezzo cliente {_eur(f['fiscali'][3])}/set]" if f["fiscali"][3] is not None else ""))
        for c in sorted(f["consegne"], key=lambda c: (c["data"], c["pid"])):
            extra = f"  [anagrafica {c['origine_cliente']}]" if c["origine_cliente"] != f["cliente_pid"] else ""
            out(f"   {c['pid']}  {_dmy(c['data'])}  " + ", ".join(f"{r['varieta']} {_n(r['qty'])}" for r in c["righe"]) + extra)
        out(f"   base {_eur(base_imp)}  IGIC {_eur(igic)}  TOTALE {_eur(base_imp + igic)}  pagato {_eur(pagato)}  saldo {_eur(max(base_imp + igic - pagato, 0))}")
    for n, m in saltati:
        out(f"\nSALTATO {n}: {m}")
    out(f"\nTOTALE da fatturare: {_eur(tot)} in {len(fatture)} fatture, da {fatture[0]['numero']} a {fatture[-1]['numero']}.")
    if not esegui:
        out("PDF in: " + str(cartella) + "\nPer emettere: stesso comando con --esegui."); conn.rollback(); return 0
    pdfs = {f["numero"]: render_pdf(f, f["numero"], giorno, emittente, pagamento, piede) for f in fatture}   # prima i PDF: se falliscono, nulla e' scritto
    corr = "genera-fatture-2026-10-31"
    for f in fatture:
        cur.execute("""INSERT INTO tpo.fatture_esterne (numero,data_emissione,cliente_id,cliente_nome,imponibile,igic,totale,tipo,stato,
                         note,fonte,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,'FATTURA','EMESSA',%s,%s,%s) RETURNING id""",
                    (f["numero"], giorno, f["cliente_pk"], f["nome"], f["base"], f["igic"], f["base"] + f["igic"],
                     "emessa da TPO (formato TP-2026-NNN)", "genera_fatture 2026-10-31", ACTOR))
        fid = cur.fetchone()[0]
        for c in f["consegne"]:
            cur.execute("INSERT INTO tpo.fatture_esterne_consegne (fattura_esterna_id,consegna_id,created_by) VALUES (%s,%s,%s)", (fid, c["pk"], ACTOR))
        cur.execute("""INSERT INTO tpo.audit_eventi (occurred_at,actor,entity_type,entity_public_id,operation,reason,before_data,after_data,
                         correlation_id,provenance) VALUES (CURRENT_TIMESTAMP,%s,'FATTURA_ESTERNA',%s,'INSERT',%s,NULL,%s::jsonb,%s,%s)""",
                    (ACTOR, f["numero"], "Fattura preparata da TPO su richiesta di Matteo il 31/10/2026",
                     json.dumps({"cliente": f["nome"], "totale": str(f["base"] + f["igic"]), "consegne": [c["pid"] for c in f["consegne"]]}),
                     f"{corr}-{f['numero']}", json.dumps({"genera_fatture": "OWNER_AUTHORIZED"})))
    conn.commit()
    cartella.mkdir(parents=True, exist_ok=True)
    for f in fatture:
        path = cartella / nome_file(f["numero"], f["nome"], giorno)
        path.write_bytes(pdfs[f["numero"]])
        out(f"   PDF: {path}")
    out(f"\nFATTO: {len(fatture)} fatture registrate e PDF scritti in {cartella}.")
    return 0


def annulla(conn, numero, giorno_fattura, giorno, cartella, esegui, out=print) -> int:
    """Annulla una FATTURA emessa con una RETTIFICATIVA R-AAAA-NNN (importi opposti) + PDF; le consegne tornano fatturabili."""
    cur = conn.cursor()
    cur.execute("""SELECT fe.id, fe.data_emissione, fe.cliente_id, fe.cliente_nome, fe.imponibile, fe.igic, fe.totale, fe.stato, fe.tipo,
                          cl.denominazione FROM tpo.fatture_esterne fe LEFT JOIN tpo.clienti cl ON cl.id = fe.cliente_id
                   WHERE fe.numero=%s AND (%s::date IS NULL OR fe.data_emissione=%s)""", (numero, giorno_fattura, giorno_fattura))
    trov = cur.fetchall()
    if len(trov) != 1:
        out(f"STOP: {numero}: trovate {len(trov)} fatture (usa --data)."); return 2
    fid, data, cli_pk, cliente_nome, imp, igic, tot, stato, tipo, denominazione = trov[0]
    if tipo != "FATTURA" or stato != "EMESSA":
        out(f"STOP: {numero} e' {tipo} {stato}: non si annulla."); return 2
    if imp is None or cli_pk is None:
        out("STOP: fattura senza importi verificati o senza cliente: l'annullo va fatto a mano."); return 2
    cur.execute("LOCK TABLE tpo.fatture_esterne IN SHARE ROW EXCLUSIVE MODE")
    cur.execute("SELECT numero FROM tpo.fatture_esterne WHERE tipo='RETTIFICATIVA'")
    mx = max([int(m.group(2)) for (n,) in cur.fetchall() if (m := re.match(r"^R-(\d{4})-(\d{3,})$", n)) and int(m.group(1)) == giorno.year] or [0])
    num_r = f"R-{giorno.year}-{mx + 1:03d}"
    out(f"== ANNULLA {numero} ({data}, {cliente_nome}, {_eur(tot)}) " + ("(ESECUZIONE)" if esegui else "(ANTEPRIMA: nulla viene scritto)"))
    out(f"   rettificativa {num_r} del {giorno.isoformat()}: importo {_eur(-tot)}; la {numero} passa ad ANNULLATA e le sue consegne tornano da fatturare.")
    if not esegui:
        out("Per annullare: stesso comando con --esegui."); conn.rollback(); return 0
    cur.execute("SELECT consegna_id FROM tpo.fatture_esterne_consegne WHERE fattura_esterna_id=%s", (fid,))
    pks = [r[0] for r in cur.fetchall()]
    cur.execute("""INSERT INTO tpo.fatture_esterne (numero,data_emissione,cliente_id,cliente_nome,imponibile,igic,totale,tipo,stato,rettifica_di,
                     note,fonte,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,'RETTIFICATIVA','EMESSA',%s,%s,%s,%s)""",
                (num_r, giorno, cli_pk, cliente_nome, -imp, -igic, -tot, numero, "annullo integrale", "genera_fatture annulla", ACTOR))
    cur.execute("UPDATE tpo.fatture_esterne SET stato='ANNULLATA' WHERE id=%s", (fid,))
    for n, op, after in ((num_r, "INSERT", {"rettifica_di": numero, "totale": str(-tot)}), (numero, "CORRECTION", {"stato": "ANNULLATA", "rettificativa": num_r})):
        cur.execute("""INSERT INTO tpo.audit_eventi (occurred_at,actor,entity_type,entity_public_id,operation,reason,before_data,after_data,
                         correlation_id,provenance) VALUES (CURRENT_TIMESTAMP,%s,'FATTURA_ESTERNA',%s,%s,%s,NULL,%s::jsonb,%s,%s)""",
                    (ACTOR, n, op, f"Annullo integrale della {numero} richiesto da Matteo il 31/10/2026 (prezzo per set del cliente)",
                     json.dumps(after), f"annulla-fattura-esterna-{numero}-{n}", json.dumps({"genera_fatture": "OWNER_AUTHORIZED"})))
    conn.commit()
    # PDF della rettificativa (stesse righe della fattura annullata, importi negativi)
    righe, pagamenti = carica_consegne(cur, pks)
    cur.execute(SQL_FISCALI + " WHERE d.cliente_id=%s", (cli_pk,))
    fis = cur.fetchone()
    cur.execute("SELECT id, public_id, data_effettiva FROM tpo.consegne WHERE id = ANY(%s)", (pks,))
    cons = [{"pk": c, "pid": p_, "data": e.astimezone(TIMEZONE).date(), "righe": righe.get(c, []), "pagamenti": []} for c, p_, e in cur.fetchall()]
    prezzo = (imp / sum((r["qty"] for c in cons for r in c["righe"]), Decimal(0))).quantize(Decimal("0.0001"))
    for c in cons:                                  # stesso prezzo della fattura annullata (importo / set)
        for r in c["righe"]:
            r["prezzo"] = prezzo
    emittente, pagamento, piede = leggi_emittente()
    path = cartella / nome_file(num_r, denominazione or cliente_nome, giorno)
    cartella.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_pdf({"nome": denominazione or cliente_nome, "fiscali": fis[1:], "consegne": cons}, num_r, giorno, emittente, pagamento, piede, rettifica=(numero, data)))
    out(f"FATTO: {num_r} registrata, {numero} ANNULLATA. PDF: {path}")
    return 0


def rigenera(conn, numero, giorno_arg, cartella, out=print) -> int:
    cur = conn.cursor()
    cur.execute("""SELECT fe.id, fe.data_emissione, fe.cliente_id, cl.denominazione, cl.public_id, fe.imponibile FROM tpo.fatture_esterne fe
                   LEFT JOIN tpo.clienti cl ON cl.id=fe.cliente_id WHERE fe.numero=%s AND (%s::date IS NULL OR fe.data_emissione=%s)""",
                (numero, giorno_arg, giorno_arg))
    trov = cur.fetchall()
    if len(trov) != 1:
        out(f"STOP: {numero}: trovate {len(trov)} fatture (usa --data se il numero e' duplicato)."); return 2
    fid, giorno, cli_pk, nome, cli_pid, imp_fattura = trov[0]
    cur.execute("SELECT consegna_id FROM tpo.fatture_esterne_consegne WHERE fattura_esterna_id=%s", (fid,))
    pks = [r[0] for r in cur.fetchall()]
    if not pks or cli_pk is None:
        out("STOP: fattura senza consegne collegate o senza cliente: non rigenerabile."); return 2
    cur.execute("SELECT id, public_id, data_effettiva FROM tpo.consegne WHERE id = ANY(%s) ORDER BY data_effettiva, public_id", (pks,))
    cons = cur.fetchall()
    righe, pagamenti = carica_consegne(cur, pks)
    cur.execute(SQL_FISCALI + " WHERE d.cliente_id=%s", (cli_pk,))
    fis = cur.fetchone()
    if fis is None:
        out("STOP: dati fiscali del cliente mancanti."); return 2
    if fis[4] is not None:
        tmp = [r for c in righe.values() for r in c]
        if sum((_q(r["qty"] * r["prezzo"]) for r in tmp), Decimal(0)) != imp_fattura:
            for r in tmp:
                r["prezzo"] = Decimal(fis[4])
    f = {"nome": nome, "fiscali": fis[1:], "consegne": [{"pk": c, "pid": p, "data": e.astimezone(TIMEZONE).date(), "righe": righe.get(c, []),
                                          "pagamenti": pagamenti.get(c, [])} for c, p, e in cons]}
    if imp_fattura is not None and totali(f["consegne"])[0] != imp_fattura:
        out(f"STOP: gli importi ricalcolati ({_eur(totali(f['consegne'])[0])}) non coincidono con la fattura registrata ({_eur(imp_fattura)}): non rigenero."); return 2
    emittente, pagamento, piede = leggi_emittente()
    path = cartella / nome_file(numero, nome, giorno)
    cartella.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_pdf(f, numero, giorno, emittente, pagamento, piede))
    out(f"PDF rigenerato: {path}"); return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mese", default="2026-10")
    ap.add_argument("--escludi", default="", help='clienti da saltare, es. "Alchimia,Oca Bianca,Splash"')
    ap.add_argument("--per-consegna", default=PER_CONSEGNA_DEFAULT)
    ap.add_argument("--unisci", default=UNISCI_DEFAULT, help="CLI-A=CLI-B,... le consegne di A vanno nella fattura di B")
    ap.add_argument("--salta-consegne", default="", help="CON-... separati da virgola: consegne gia' fatturate altrove, da non includere")
    ap.add_argument("--data-emissione", default=None)
    ap.add_argument("--cartella", default=str(CARTELLA))
    ap.add_argument("--rigenera", metavar="NUMERO")
    ap.add_argument("--annulla", metavar="NUMERO", help="annulla la fattura con una rettificativa R-AAAA-NNN (usa --data-emissione per la data della rettificativa)")
    ap.add_argument("--data", help="con --rigenera: data della fattura se il numero e' duplicato")
    ap.add_argument("--esegui", action="store_true")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    prm = load_postgresql_parameters()
    conn = psycopg.connect(host=prm["host"], port=prm["port"], dbname=prm["dbname"], user=prm["user"], password=prm["password"],
                           sslmode=prm["sslmode"], connect_timeout=prm["connect_timeout"])
    try:
        cartella = Path(a.cartella).expanduser()
        if a.annulla:
            giorno_r = date.fromisoformat(a.data_emissione) if a.data_emissione else datetime.now(TIMEZONE).date()
            return annulla(conn, a.annulla, date.fromisoformat(a.data) if a.data else None, giorno_r, cartella, a.esegui)
        if a.rigenera:
            return rigenera(conn, a.rigenera, date.fromisoformat(a.data) if a.data else None, cartella)
        giorno = date.fromisoformat(a.data_emissione) if a.data_emissione else datetime.now(TIMEZONE).date()
        unisci = dict(p.split("=") for p in a.unisci.split(",") if "=" in p)
        return run(conn, a.mese, [e.strip() for e in a.escludi.split(",") if e.strip()],
                   [e.strip() for e in a.per_consegna.split(",") if e.strip()], unisci, giorno, cartella, a.esegui,
                   [c.strip() for c in a.salta_consegne.split(",") if c.strip()])
    except (Stop, ValueError) as exc:
        print(f"STOP: {exc}"); return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
