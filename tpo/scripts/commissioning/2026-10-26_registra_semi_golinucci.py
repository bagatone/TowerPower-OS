"""Registra l'arrivo dei semi Golinucci del 25/10/2026 (12 sacchi, foto di Matteo del 26/10 e 27/10).

Per ogni sacco, nell'ordine e solo se manca ancora:
  1. VARIETA nuova (`tpo onboarding variety`) con sigla di 3 lettere PERMANENTE (le 8 varieta' nuove);
  2. SEMENTE (`tpo semente commission`) fornitore + referenza commerciale come sull'etichetta;
  3. LOTTO_SEME (`tpo seed-lot commission`) con codice lotto ESATTO dell'etichetta, ricevuto il 25/10/2026,
     scadenza = ultimo giorno del mese "Best before" (31/10/2027);
  4. SEMENTE_IMPIEGO (`tpo semente-impiego commission`) SOLO per Cilantro e Girasole, che hanno gia' un protocollo.
     Le 8 varieta' nuove non hanno ancora protocollo (i valori li dichiara Matteo): il collegamento seme -> protocollo
     si fa dopo, con 2026-10-12_protocolli_nuovi.py.

CASI PARTICOLARI
  - Afila: il lotto nuovo (GOL 0708/BM2643) va sulla SEMENTE Golinucci gia' esistente (codice diverso dal vecchio).
  - Cilantro: il codice sul sacco (GOL 0927/BM7442) e' IDENTICO a quello del vecchio lotto LSE-000013 e il database non
    ammette due lotti con lo stesso codice sulla stessa semente: il lotto va su una SEMENTE nuova ("Coriander Split 2026-10")
    con il codice esatto dell'etichetta, collegata al protocollo Cilantro.
  - Girasole Golinucci: 2 sacchi da 1 kg con lo stesso codice = UN lotto da 2000 g, su SEMENTE nuova (il girasole a magazzino e'
    Hyfarm).

Senza --esegui NON scrive nulla (anteprima). Rilanciabile: cio' che esiste gia' viene saltato.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-26_registra_semi_golinucci.py            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-26_registra_semi_golinucci.py --esegui

COMANDI CORRETTIVI: varieta', semente e lotto creati non si cancellano. Se un grammo o un codice e' sbagliato:
  .venv/bin/python scripts/commissioning/2026-10-21_rettifica_lotto_seme.py --help
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")

FORNITORE = "Golinucci Organic"
RICEVUTO = date(2026, 10, 25)
SCADENZA = date(2027, 10, 31)  # etichetta: "Best before: October 2027" -> ultimo giorno del mese
TAG = "SEMI-GOLINUCCI-2026-10-25"
ACTOR = "matteo"

# nome varieta' a sistema, sigla (None = esiste gia'), referenza commerciale (etichetta), codice lotto, grammi, note
SACCHI = [
    {"varieta": "Afila", "sigla": None, "referenza": None, "cerca": ("affila", "afila"), "lotto": "GOL 0708/BM2643",
     "grammi": Decimal("5000"), "formato": "5 kg", "etichetta": "Pea Green Affila"},
    {"varieta": "Cilantro", "sigla": None, "referenza": "Coriander Split 2026-10", "lotto": "GOL 0927/BM7442",
     "grammi": Decimal("2500"), "formato": "2,5 kg", "impiego": True,
     "nota": "stesso codice del vecchio LSE-000013: semente nuova per non violare l'unicita' semente+codice lotto"},
    {"varieta": "Girasole", "sigla": None, "referenza": "Sunflower", "lotto": "GOL 0968/BM2537",
     "grammi": Decimal("2000"), "formato": "2 sacchi da 1 kg", "impiego": True, "qta_fonte": "OWNER_AUTHORIZED",
     "nota": "2 sacchi da 1 kg con lo stesso codice = un lotto da 2000 g"},
    {"varieta": "Melissa", "sigla": "MEL", "referenza": "Lemon Balm", "lotto": "GOL 0013/BA2412",
     "grammi": Decimal("100"), "formato": "100 g"},
    {"varieta": "Perilla", "sigla": "SHI", "referenza": "Perilla Bicolor", "lotto": "GOL 0020/BA7340",
     "grammi": Decimal("50"), "formato": "50 g"},
    {"varieta": "Broccolo", "sigla": "BRO", "referenza": "Broccoli Calabrese", "lotto": "GOL 0913/BM2482",
     "grammi": Decimal("500"), "formato": "500 g"},
    {"varieta": "Bieta gialla", "sigla": "BIG", "referenza": "Beet Yellow", "lotto": "GOL 0912/BM2481",
     "grammi": Decimal("500"), "formato": "500 g"},
    {"varieta": "Bieta rossa", "sigla": "BIR", "referenza": "Beet Bull's Blood", "lotto": "GOL 0910/BM2479",
     "grammi": Decimal("500"), "formato": "500 g"},
    {"varieta": "Nasturzio", "sigla": "NAS", "referenza": "Nasturtium Empress of India", "lotto": "GOL 0016/BA7442",
     "grammi": Decimal("500"), "formato": "500 g"},
    {"varieta": "Lupino", "sigla": "LUP", "referenza": "Lupine Sweet", "lotto": "GOL 0985/BM7508",
     "grammi": Decimal("500"), "formato": "500 g"},
    {"varieta": "Prezzemolo", "sigla": "PRE", "referenza": "Parsley", "lotto": "GOL 0953/BM2522",
     "grammi": Decimal("500"), "formato": "500 g"},
    {"varieta": "Mais", "sigla": "MAI", "referenza": "Mais", "lotto": "GOL 0705/BM7315",
     "grammi": Decimal("500"), "formato": "500 g"},
]


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _n(value: Decimal) -> str:
    return format(Decimal(value).normalize(), "f")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _mostra(argv) -> str:
    return "tpo " + " ".join(a if re.fullmatch(r"[\w./:+=,@-]+", a) else repr(a) for a in argv)


def _comando_varieta(vid, nome, sigla):
    return ["onboarding", "variety", "--variety-id", vid, "--denomination", nome, "--traceability-code", sigla,
            "--state", "ATTIVA", "--actor", ACTOR,
            "--reason", f"Nuova varieta' {nome} ({sigla}): primo arrivo semi Golinucci del 25/10/2026, nome e sigla dichiarati da Matteo",
            "--correlation-id", f"{TAG}-varieta-{_slug(nome)}"]


def _comando_semente(s, marca, trattamento, certificazioni):
    argv = ["semente", "commission", "--fornitore", FORNITORE, "--referenza-commerciale", s["referenza"],
            "--formato", s["formato"]]
    if marca:
        argv += ["--marca", marca]
    if trattamento:
        argv += ["--trattamento", trattamento]
    if certificazioni:
        argv += ["--certificazioni", certificazioni]
    key = f"{TAG}-semente-{_slug(s['referenza'])}"
    return argv + ["--actor", ACTOR, "--reason",
                   f"Semente {FORNITORE} {s['referenza']} ({s['varieta']}): arrivo del 25/10/2026 (etichetta)",
                   "--correlation-id", key, "--idempotency-key", key, "--confirm"]


def _comando_lotto(s, referenza):
    qta_fonte = s.get("qta_fonte", "LABEL_OR_PACKAGE")
    prov = {"seed_supplier": "LABEL_OR_PACKAGE", "seed_commercial_reference": "LABEL_OR_PACKAGE",
            "manufacturer_lot_number": "LABEL_OR_PACKAGE", "received_date": "OWNER_AUTHORIZED",
            "expiry_date": "OWNER_AUTHORIZED", "initial_quantity": qta_fonte, "unit": "LABEL_OR_PACKAGE",
            "anomaly": "UNKNOWN"}
    key = f"{TAG}-lotto-{_slug(s['lotto'])}"
    return ["seed-lot", "commission", "--seed-supplier", FORNITORE, "--seed-commercial-reference", referenza,
            "--manufacturer-lot-number", s["lotto"], "--received-date", RICEVUTO.isoformat(),
            "--expiry-date", SCADENZA.isoformat(), "--initial-quantity", _n(s["grammi"]), "--unit", "GRAM",
            "--provenance", json.dumps(prov), "--actor", ACTOR,
            "--reason", (f"Arrivo {FORNITORE} del 25/10/2026: {referenza}, lotto {s['lotto']}, {_n(s['grammi'])} g "
                         f"(etichetta; scadenza = fine del mese 'Best before October 2027')"),
            "--correlation-id", key, "--idempotency-key", key, "--confirm"]


def _comando_impiego(referenza, pv, varieta):
    key = f"{TAG}-impiego-{_slug(referenza)}"
    return ["semente-impiego", "commission", "--fornitore", FORNITORE, "--referenza-commerciale", referenza,
            "--protocol-version", pv, "--raccomandazione", "RACCOMANDATA",
            "--motivazione", f"Seme {FORNITORE} {referenza} arrivato il 25/10/2026, usato per {varieta} (dichiarato da Matteo)",
            "--actor", ACTOR, "--reason", f"Collegamento seme {FORNITORE} {referenza} al protocollo {varieta}",
            "--correlation-id", key, "--idempotency-key", key, "--confirm"]


def run(conn, esegui: bool, esegui_tpo=None, out=print) -> int:
    conn.read_only = True
    cur = conn.cursor()

    def q(sql, args=()):
        cur.execute(sql, args)
        return cur.fetchall()

    out(f"== SEMI GOLINUCCI 25/10/2026 -- {'ESECUZIONE' if esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    varieta = {_fold(d): (p, i) for p, d, i in q("SELECT public_id, denominazione, id FROM tpo.varieta")}
    codici_usati = {c: d for d, c in q("SELECT denominazione, codice_tracciabilita FROM tpo.varieta "
                                       "WHERE codice_tracciabilita IS NOT NULL")}
    numeri = [int(m.group(1)) for (p,) in q("SELECT public_id FROM tpo.varieta") if (m := re.fullmatch(r"VAR-(\d+)", p))]
    prossimo = max(numeri or [0]) + 1
    sementi = {(_fold(f), _fold(r)): (i, f, r, m, t, c)
               for i, f, r, m, t, c in q("SELECT id, fornitore, referenza_commerciale, marca, trattamento, certificazioni "
                                         "FROM tpo.sementi")}

    piano, errori = [], []
    modello = None  # marca/trattamento/certificazioni copiati dalle sementi Golinucci gia' presenti
    for (f, r), v in sementi.items():
        if f == _fold(FORNITORE):
            modello = (v[3], v[4], v[5])
            break
    for s in SACCHI:
        nome = s["varieta"]
        riga = {"s": s, "passi": []}
        trovata = varieta.get(_fold(nome))
        if trovata is None:
            if s["sigla"] is None:
                errori.append(f"{nome}: varieta' non trovata a sistema (attesa gia' esistente).")
                continue
            if s["sigla"] in codici_usati:
                errori.append(f"{nome}: la sigla {s['sigla']} e' gia' di {codici_usati[s['sigla']]}.")
                continue
            vid = f"VAR-{prossimo:06d}"
            prossimo += 1
            riga["passi"].append(("VARIETA nuova", f"{vid} {nome} [{s['sigla']}] ATTIVA",
                                  _comando_varieta(vid, nome, s["sigla"])))
            codici_usati[s["sigla"]] = nome
        elif s["sigla"]:
            riga["passi"].append(("VARIETA", f"{trovata[0]} {nome} esiste gia': salto", None))
        referenza = s["referenza"]
        if referenza is None:
            cand = [v for (f, r), v in sementi.items() if f == _fold(FORNITORE) and any(w in r for w in s["cerca"])]
            if len(cand) != 1:
                errori.append(f"{nome}: trovate {len(cand)} sementi Golinucci compatibili con {s['cerca']} (attesa 1).")
                continue
            semente_id, referenza = cand[0][0], cand[0][2]
            riga["passi"].append(("SEMENTE", f"esistente: {FORNITORE} / {referenza}", None))
        else:
            esistente = sementi.get((_fold(FORNITORE), _fold(referenza)))
            if esistente:
                semente_id = esistente[0]
                riga["passi"].append(("SEMENTE", f"{FORNITORE} / {referenza} esiste gia': salto", None))
            else:
                semente_id = None
                riga["passi"].append(("SEMENTE nuova", f"{FORNITORE} / {referenza} ({s['formato']})",
                                      _comando_semente(s, *(modello or (None, None, None)))))
        gia = (q("SELECT public_id, quantita_iniziale FROM tpo.lotti_seme WHERE semente_id=%s AND numero_lotto_produttore=%s",
                 (semente_id, s["lotto"])) if semente_id is not None else [])
        if gia:
            riga["passi"].append(("LOTTO", f"{gia[0][0]} {s['lotto']} esiste gia' ({gia[0][1]} g): salto", None))
        else:
            riga["passi"].append(("LOTTO nuovo", f"{s['lotto']}  {_n(s['grammi'])} g  ricevuto {RICEVUTO:%d/%m/%Y}  "
                                                  f"scade {SCADENZA:%d/%m/%Y}", _comando_lotto(s, referenza)))
        if s.get("impiego"):
            pv = q("""SELECT pv.public_id FROM tpo.protocollo_versioni pv
                      JOIN tpo.protocolli p ON p.id = pv.protocollo_id
                      JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id
                      JOIN tpo.cultivar c ON c.id = cu.cultivar_id
                      JOIN tpo.varieta v ON v.id = c.varieta_id
                      JOIN tpo.usi_produttivi up ON up.id = cu.uso_produttivo_id AND up.codice = 'MICROGREEN'
                      WHERE v.denominazione = %s AND pv.stato_approvazione = 'APPROVATA' AND pv.valida_al IS NULL""", (nome,))
            if len(pv) != 1:
                errori.append(f"{nome}: trovati {len(pv)} protocolli approvati correnti (atteso 1).")
                continue
            if semente_id is not None and q("SELECT 1 FROM tpo.semente_impieghi WHERE semente_id=%s", (semente_id,)):
                riga["passi"].append(("IMPIEGO", "collegamento seme -> protocollo gia' presente: salto", None))
            else:
                riga["passi"].append(("IMPIEGO", f"seme -> protocollo {nome} ({pv[0][0]}) RACCOMANDATA",
                                      _comando_impiego(referenza, pv[0][0], nome)))
        piano.append(riga)
    conn.rollback()

    for riga in piano:
        s = riga["s"]
        out(f"\n--- {s['varieta']}  ({s['referenza'] or s['etichetta']})" + (f"   NOTA: {s['nota']}" if s.get("nota") else ""))
        for tipo, testo, argv in riga["passi"]:
            out(f"  {tipo:14} {testo}")
    if errori:
        out("\nSTOP: " + "\n      ".join(errori))
        return 2
    da_fare = [(tipo, argv) for riga in piano for tipo, _t, argv in riga["passi"] if argv]
    out(f"\nDa scrivere: {len(da_fare)} operazioni. Le 8 varieta' nuove restano SENZA protocollo (valori da dichiarare): "
        "il seme non e' ancora usabile per le semine finche' non si crea il protocollo e il collegamento.")
    if not esegui:
        out("\n(anteprima: nulla scritto; per scrivere aggiungi --esegui)")
        return 0
    for tipo, argv in da_fare:
        out(f"\n  $ {_mostra(argv)[:200]}")
        codice, testo = esegui_tpo(argv)
        out("    " + testo.strip().replace("\n", "\n    "))
        if codice != 0:
            out(f"\nSTOP: {tipo} fallito (exit {codice}). Rilancia lo script: cio' che esiste gia' viene saltato.")
            return 1
    out("\nFATTO. Correttivi: 2026-10-21_rettifica_lotto_seme.py (grammi); varieta', semente e lotto non si cancellano.")
    return 0


def _esegui_tpo(argv):
    done = subprocess.run([RUN, *argv], capture_output=True, text=True)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, a.esegui, _esegui_tpo)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
