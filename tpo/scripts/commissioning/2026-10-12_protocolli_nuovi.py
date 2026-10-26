"""Crea i PROTOCOLLI agronomici mancanti di Cavolo rosso (Col roja) e Girasole - 12/10/2026, richiesta di Matteo.

Servono per poter registrare le semine di stamattina (senza protocollo approvato il sistema non semina). Per ognuna:
  1. `tpo protocollo commission` : uso produttivo + cultivar + protocollo + versione 1 APPROVATA, valida dal 12/10/2026;
  2. `tpo semente-impiego commission` : collega il seme Hyfarm gia' a magazzino a quel protocollo (RACCOMANDATA),
     altrimenti lo script delle semine non trova nessun lotto da usare.

TEMPI DICHIARATI DA MATTEO (12/10/2026)
  Cavolo rosso : nessuna idratazione, 4 gg germinazione, 8 gg luce/crescita, 10 g di seme per SET,
                 si consegna al massimo 8 giorni dopo la raccolta
  Girasole     : 12 h idratazione, 6 gg germinazione, 6 gg luce/crescita, 28 g di seme per SET,
                 si consegna al massimo 5 giorni dopo la raccolta
ALTRI CAMPI non dichiarati (anticipo minimo di raccolta, buffer, orari di semina/raccolta, resa, granularita'): copiati
dal protocollo corrente di Pak Choi (modificabile con --modello), MOSTRATI in anteprima con la scritta "copiato". Se
non vanno bene, dimmelo prima di --esegui; dopo si possono rivedere con 2026-10-07_revisiona_protocollo.py (nuova
versione, non retroattiva).

Senza --esegui NON scrive nulla (anteprima). Rilanciabile: cio' che esiste gia' viene saltato.
Richiede la migrazione 20261020_0039.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-12_protocolli_nuovi.py            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-12_protocolli_nuovi.py --esegui

COMANDO CORRETTIVO: un protocollo creato non si cancella; per cambiare un valore si fa una nuova versione, es.
  .venv/bin/python scripts/commissioning/2026-10-07_revisiona_protocollo.py "Girasole" --g-per-set 30 --motivo "..." --esegui
(a fine esecuzione lo script stampa i comandi con i nomi esatti).
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

BASE_SCRIPT = ROOT / "scripts" / "commissioning" / "2026-10-08_consegne_giornata.py"
HEAD = "20261020_0039"
VALIDO_DAL = date(2026, 10, 12)
PROVENANCE = "OWNER_AUTHORIZED_REAL_GROWING_PROTOCOL_2026-10"
# l'uso produttivo condiviso "Microgreens" fu creato dall'attore di sistema tpo.owner e la scrittura governata richiede lo
# STESSO attore (con "matteo" fallisce: USO_PRODUTTIVO incompatibile, verificato il 12/10; stessa cosa il 15/9 con "giulia")
ACTOR_PROTOCOLLO = "tpo.owner"
MODELLO_DEFAULT = "Pak Choi"
# varieta' a sistema -> tempi dichiarati da Matteo + come riconoscere il seme a magazzino
NUOVI = [
    {"nome": "Cavolo rosso", "idratazione": Decimal("0"), "germinazione": 4, "luce": 8, "g_per_set": Decimal("10"),
     "lead_max": 8, "seme": ("col roja", "cavolo rosso", "col rosso")},
    {"nome": "Girasole", "idratazione": Decimal("12"), "germinazione": 6, "luce": 6, "g_per_set": Decimal("28"),
     "lead_max": 5, "seme": ("girasol", "sunflower")},
]
TEMPLATE_SQL = """
SELECT v.public_id, v.denominazione, c.denominazione, up.codice, up.denominazione, p.denominazione,
       pv.orario_semina_previsto, pv.orario_raccolta_target, pv.resa_attesa, pv.granularita_produttiva,
       pv.harvest_min_lead_giorni, pv.buffer_temporale_minuti, pv.public_id, pv.harvest_max_lead_giorni
FROM tpo.protocollo_versioni pv
JOIN tpo.protocolli p ON p.id = pv.protocollo_id
JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id
JOIN tpo.cultivar c ON c.id = cu.cultivar_id
JOIN tpo.varieta v ON v.id = c.varieta_id
JOIN tpo.usi_produttivi up ON up.id = cu.uso_produttivo_id AND up.codice = 'MICROGREEN'
WHERE pv.stato_approvazione = 'APPROVATA' AND pv.valida_al IS NULL"""

_BASE = None


def carica_base():
    global _BASE
    if _BASE is not None:
        return _BASE
    spec = importlib.util.spec_from_file_location("consegne_giornata_base", BASE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.HEAD = HEAD
    _BASE = module
    return module


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").strip()


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def trova_varieta(ctx, nome):
    for pid, den in ctx.q("SELECT public_id, denominazione FROM tpo.varieta"):
        if _fold(den) == _fold(nome):
            return pid, den
    return None


def protocolli_correnti(ctx, variety_public_id):
    return [r for r in ctx.q(TEMPLATE_SQL) if r[0] == variety_public_id]


def leggi_modello(b, ctx, nome):
    v = trova_varieta(ctx, nome)
    if not v:
        raise b.Stop(f"modello '{nome}': varieta' non trovata.")
    righe = protocolli_correnti(ctx, v[0])
    if len(righe) != 1:
        raise b.Stop(f"modello '{nome}': trovati {len(righe)} protocolli approvati correnti, atteso 1.")
    return righe[0]


def trova_semente(b, ctx, parole, variety_name):
    rows = ctx.q("""SELECT s.id, s.fornitore, s.referenza_commerciale,
                           COALESCE((SELECT sum(l.quantita_residua) FROM tpo.lotti_seme l WHERE l.semente_id=s.id),0)
                    FROM tpo.sementi s WHERE s.attiva""")
    trovate = [r for r in rows if any(p in _fold(r[2]) for p in parole)]
    if len(trovate) != 1:
        raise b.Stop(f"{variety_name}: trovate {len(trovate)} sementi a magazzino compatibili con "
                     f"{' / '.join(parole)} (atteso 1): "
                     + (", ".join(f"{r[1]} {r[2]}" for r in trovate) or "nessuna") + ". Dimmi quale.")
    return trovate[0]


def impiego_esiste(ctx, semente_id, variety_public_id):
    row = ctx.one("""SELECT 1 FROM tpo.semente_impieghi si
                     JOIN tpo.cultivar_usi cu ON cu.id = si.cultivar_uso_id
                     JOIN tpo.cultivar c ON c.id = cu.cultivar_id
                     JOIN tpo.varieta v ON v.id = c.varieta_id
                     WHERE si.semente_id = %s AND v.public_id = %s""", (semente_id, variety_public_id))
    return row is not None


def prepara(b, ctx, modello_nome):
    """Valida tutto e costruisce il piano; non scrive."""
    ctx.check_head()
    m = leggi_modello(b, ctx, modello_nome)
    (_, m_var, m_cult, up_code, up_name, m_prot, sowing, harvest, resa, gran, lead_min, buffer, m_pv, m_lead_max) = m
    numeri = [int(x.group(1)) for (pid,) in ctx.q("SELECT public_id FROM tpo.protocollo_versioni")
              if (x := re.fullmatch(r"PV-(\d+)", pid))]
    prossimo = max(numeri or [0]) + 1
    piano = []
    for spec in NUOVI:
        trovata = trova_varieta(ctx, spec["nome"])
        if not trovata:
            raise b.Stop(f"varieta' '{spec['nome']}' non trovata a sistema.")
        vid, den = trovata
        lead_copiato = spec["lead_max"] is None
        if lead_copiato:
            spec = {**spec, "lead_max": m_lead_max}   # non dichiarato: copiato dal modello e MOSTRATO come tale
        if lead_min > spec["lead_max"]:
            raise b.Stop(f"{den}: anticipo minimo copiato da {m_var} ({lead_min} gg) supera il massimo dichiarato "
                         f"({spec['lead_max']} gg): dimmi quale minimo usare.")
        semente = trova_semente(b, ctx, spec["seme"], den)
        esistenti = protocolli_correnti(ctx, vid)
        if len(esistenti) > 1:
            raise b.Stop(f"{den}: {len(esistenti)} protocolli correnti, atteso 0 o 1.")
        pv = esistenti[0][12] if esistenti else f"PV-{prossimo:06d}"
        if not esistenti:
            prossimo += 1
        piano.append({
            **spec, "lead_copiato": lead_copiato, "valido_dal": spec.get("valido_dal", VALIDO_DAL), "variety_id": vid, "denominazione": den, "esiste": bool(esistenti), "pv": pv,
            "cultivar": den, "protocollo": f"Protocollo {den}",
            "uso_codice": up_code, "uso_nome": up_name,
            "semina": sowing, "raccolta": harvest, "resa": resa, "granularita": gran, "lead_min": lead_min,
            "buffer": buffer, "modello": m_var, "semente": semente,
            "impiego_esiste": impiego_esiste(ctx, semente[0], vid)})
    return piano


def mostra(piano):
    for p in piano:
        s = p["semente"]
        print(f"\n=== {p['denominazione']} ({p['variety_id']}) -> {p['pv']}"
              + ("  [PROTOCOLLO GIA' ESISTENTE: salto]" if p["esiste"] else ""))
        print(f"  dichiarati da Matteo : idratazione {_n(p['idratazione'])} h, germinazione {p['germinazione']} gg, "
              f"luce/crescita {p['luce']} gg, {_n(p['g_per_set'])} g/SET"
              + ("" if p["lead_copiato"] else f", consegna entro {p['lead_max']} gg dalla raccolta"))
        if p["lead_copiato"]:
            print(f"  copiato da {p['modello']:8}: consegna entro {p['lead_max']} gg dalla raccolta (non dichiarato)")
        print(f"  copiati da {p['modello']:8}: anticipo minimo {p['lead_min']} gg, buffer {p['buffer']} min, "
              f"semina {p['semina']}, raccolta {p['raccolta']}, resa {_n(p['resa'])} SET, granularita' {_n(p['granularita'])}")
        print(f"  nomi                 : cultivar '{p['cultivar']}', protocollo '{p['protocollo']}', "
              f"uso {p['uso_codice']} ({p['uso_nome']}), valido dal {p['valido_dal']}")
        avviso = ""
        if Decimal(s[3]) < p["g_per_set"]:
            avviso = f"  ATTENZIONE: il seme a magazzino ({_n(s[3])} g) non basta per 1 SET ({_n(p['g_per_set'])} g)"
        print(f"  seme                 : {s[1]} / {s[2]}, residuo totale {_n(s[3])} g"
              + (" [collegamento gia' presente: salto]" if p["impiego_esiste"] else " -> collegamento RACCOMANDATA")
              + avviso)


def comando_protocollo(p, adesso):
    corr = f"PROTOCOLLO-2026-10-12-{_fold(p['denominazione']).replace(' ', '-')}"
    contenuto = (f"Protocollo standard {p['denominazione']}: idratazione {_n(p['idratazione'])} h, germinazione "
                 f"{p['germinazione']} gg, luce/crescita {p['luce']} gg, {_n(p['g_per_set'])} g di seme per SET, "
                 f"consegna entro {p['lead_max']} gg dalla raccolta.")
    return ["protocollo", "commission", "--variety-id", p["variety_id"], "--variety-name", p["denominazione"],
            "--cultivar-name", p["cultivar"], "--productive-use-code", p["uso_codice"],
            "--productive-use-name", p["uso_nome"], "--protocol-name", p["protocollo"],
            "--protocol-version-id", p["pv"], "--version", "1", "--valid-from", p["valido_dal"].isoformat(),
            "--hydration-hours", _n(p["idratazione"]), "--planned-sowing-time", str(p["semina"]),
            "--target-harvest-time", str(p["raccolta"]), "--germination-days", str(p["germinazione"]),
            "--light-growth-days", str(p["luce"]), "--seed-grams-per-set", _n(p["g_per_set"]),
            "--expected-yield", _n(p["resa"]), "--production-granularity", _n(p["granularita"]),
            "--harvest-min-lead-days", str(p["lead_min"]), "--harvest-max-lead-days", str(p["lead_max"]),
            "--temporal-buffer-minutes", str(p["buffer"]), "--content", contenuto,
            "--motivation", f"{p['denominazione']} seminato senza protocollo a sistema: tempi reali di campo "
                            f"dichiarati da Matteo il {p['valido_dal']:%d/%m/%Y} per poter registrare la semina.",
            "--evidence", f"Dichiarazione di Matteo (esperienza di campo del {p['valido_dal']:%d/%m/%Y})",
            "--provenance", PROVENANCE, "--actor", ACTOR_PROTOCOLLO,
            "--reason", f"Nuovo protocollo {p['denominazione']} (tempi dichiarati da Matteo il {p['valido_dal']:%d/%m/%Y})",
            "--correlation-id", corr, "--confirm"]


def comando_impiego(p):
    s = p["semente"]
    key = f"impiego-2026-10-12-{_fold(p['denominazione']).replace(' ', '-')}"
    return ["semente-impiego", "commission", "--fornitore", s[1], "--referenza-commerciale", s[2],
            "--protocol-version", p["pv"], "--raccomandazione", "RACCOMANDATA",
            "--motivazione", f"Seme {s[1]} {s[2]} gia' a magazzino, usato per {p['denominazione']} (dichiarato da Matteo)",
            "--actor", "matteo", "--reason",
            f"Collegamento seme {s[1]} {s[2]} al protocollo {p['denominazione']} ({p['valido_dal']:%d/%m/%Y})",
            "--correlation-id", key, "--idempotency-key", key, "--confirm"]


def run(ctx, modello=MODELLO_DEFAULT, nuovi=None) -> int:
    global NUOVI
    b = carica_base()
    if nuovi:
        NUOVI = nuovi
    oggi = datetime.now().astimezone().date()
    for spec in NUOVI:
        dal = spec.get("valido_dal", VALIDO_DAL)
        if oggi < dal:
            raise b.Stop(f"oggi ({oggi}) e' prima del {dal}: il protocollo non sarebbe ancora valido.")
    print(f"== PROTOCOLLI NUOVI -- {'ESECUZIONE' if ctx.execute else 'ANTEPRIMA (nulla viene scritto)'}")
    piano = prepara(b, ctx, modello)
    mostra(piano)
    for p in piano:
        if not p["esiste"]:
            ctx.tpo(comando_protocollo(p, oggi), f"protocollo {p['denominazione']} ({p['pv']})")
        if not p["impiego_esiste"]:
            ctx.tpo(comando_impiego(p), f"collegamento seme -> {p['denominazione']}")
    print("\nCOMANDO CORRETTIVO (un protocollo creato non si cancella: per cambiare un valore si crea una nuova versione):")
    for p in piano:
        print(f'  .venv/bin/python scripts/commissioning/2026-10-07_revisiona_protocollo.py "{p["denominazione"]}" '
              f'--germinazione {p["germinazione"]} --luce {p["luce"]} --g-per-set {_n(p["g_per_set"])} '
              f'--motivo "..." --esegui    (metti solo i campi da cambiare)')
    print("\n== FINE" + ("" if ctx.execute else " (anteprima: nulla scritto; per scrivere aggiungi --esegui)"))
    if not ctx.execute:
        print("Poi: registra le semine con 2026-10-12_semine.py (anteprima e --esegui).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    ap.add_argument("--modello", default=MODELLO_DEFAULT, help="varieta' da cui copiare i campi non dichiarati")
    ap.add_argument("--varieta", help="crea il protocollo di UNA varieta' a scelta (al posto di Cavolo rosso/Girasole)")
    ap.add_argument("--idratazione", type=Decimal, default=Decimal("0"), help="ore di idratazione")
    ap.add_argument("--germinazione", type=int, help="giorni di germinazione")
    ap.add_argument("--luce", type=int, help="giorni di luce/crescita")
    ap.add_argument("--g-per-set", type=Decimal, help="grammi di seme per SET")
    ap.add_argument("--consegna-entro", type=int, help="giorni massimi tra raccolta e consegna (default: come il modello)")
    ap.add_argument("--seme", help="parole (separate da virgola) per riconoscere il seme a magazzino")
    ap.add_argument("--valido-dal", help="AAAA-MM-GG (default: oggi)")
    a = ap.parse_args()
    nuovi = None
    if a.varieta:
        mancano = [n for n, v in (("--germinazione", a.germinazione), ("--luce", a.luce), ("--g-per-set", a.g_per_set),
                                  ("--seme", a.seme)) if v is None]
        if mancano:
            print(f"STOP: con --varieta servono anche {', '.join(mancano)}.", file=sys.stderr)
            return 1
        dal = date.fromisoformat(a.valido_dal) if a.valido_dal else datetime.now().astimezone().date()
        nuovi = [{"nome": a.varieta, "idratazione": a.idratazione, "germinazione": a.germinazione, "luce": a.luce,
                  "g_per_set": a.g_per_set, "lead_max": a.consegna_entro, "valido_dal": dal,
                  "seme": tuple(x.strip().lower() for x in a.seme.split(",") if x.strip())}]
    b = carica_base()
    ctx = b.Ctx(a.esegui, Path.home() / "Desktop" / "bolle")
    try:
        return run(ctx, a.modello, nuovi)
    except b.Stop as exc:
        print(f"\nSTOP: {exc}", file=sys.stderr)
        return 1
    finally:
        ctx.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
