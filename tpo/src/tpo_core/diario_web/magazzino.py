"""Schermata MAGAZZINO del diario (17/10/2026): semi, materiali e semine in coltivazione. SOLA LETTURA.

Stessi numeri e stessa logica di scripts/commissioning/2026-10-15_inventario.py e 2026-10-16_semine_in_corso.py,
ma come dati per la pagina. Sono i numeri del SISTEMA, non un conteggio fisico: il residuo di un lotto scende solo
quando una semina viene registrata con quel lotto; la giacenza degli articoli solo con carichi, consumi e rettifiche.

Regola di consumo: 4 vaschette + 4 substrati per SET seminato. I SET in coltivazione sono i SET ATTESI registrati sulla
semina (germinazione + luce + crescita; LUCE e CRESCITA sono lo stesso processo); AVVIATA e PRONTA_ALLA_RACCOLTA si
mostrano a parte e non entrano nel totale. Una semina senza resa attesa compare come "SET ?" e non viene contata.

Nessuna scrittura: la connessione e' aperta in sola lettura (guardia D del freeze OPERATIONAL_WEB_ADAPTER).
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence

from . import db_context
from ..infrastructure.postgresql.settings import PostgreSQLSettings

PEZZI_PER_SET = Decimal(4)
STADI = ("AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA")
IN_SEMINA = ("GERMINAZIONE", "LUCE", "CRESCITA")

SQL_LOTTI = """SELECT l.public_id, s.fornitore, s.referenza_commerciale, l.numero_lotto_produttore, l.data_ricezione,
       l.data_scadenza, l.quantita_iniziale, l.quantita_residua, l.unita_misura::text, l.anomalia,
       COALESCE((SELECT string_agg(DISTINCT v.denominazione, ', ' ORDER BY v.denominazione)
                 FROM tpo.semine se JOIN tpo.varieta v ON v.id=se.varieta_id WHERE se.lotto_seme_id=l.id), '')
FROM tpo.lotti_seme l JOIN tpo.sementi s ON s.id=l.semente_id
ORDER BY lower(s.referenza_commerciale), lower(s.fornitore), l.data_ricezione, l.public_id"""

SQL_ARTICOLI = """SELECT a.public_id, a.denominazione, a.unita_misura::text, COALESCE(st.disponibile, 0),
       (SELECT max(m.data_movimento) FROM tpo.movimenti_magazzino m WHERE m.articolo_id=a.id)
FROM tpo.articoli a LEFT JOIN tpo.stock_articoli st ON st.articolo_id=a.id
ORDER BY lower(a.denominazione), a.public_id"""

SQL_SEMINE = """SELECT s.public_id, s.codice_tracciabilita, v.denominazione, s.stato::text, s.data_avvio,
       s.expected_useful_quantity, s.expected_useful_uom::text,
       COALESCE((SELECT SUM(rc.quantita) FROM tpo.raccolte rc WHERE rc.semina_id=s.id AND rc.unita_misura='SET'),0)
FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
WHERE s.stato<>'CHIUSA' ORDER BY v.denominazione, s.data_avvio, s.public_id"""


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def _n(value: Any) -> str:
    """Decimale leggibile, senza zeri inutili ("2.50" -> "2.5", "100" -> "100")."""
    text = format(Decimal(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _giorno(value: Any) -> str | None:
    return value.date().isoformat() if isinstance(value, datetime) else (value.isoformat() if value else None)


def _semi(lotti: Sequence[Sequence[Any]]) -> dict:
    referenze: dict[str, dict] = {}
    totale = Decimal(0)
    for lse, fornitore, referenza, numero, ricevuto, scadenza, iniziale, residuo, uom, anomalia, varieta in lotti:
        gruppo = referenze.setdefault(referenza, {"referenza": referenza, "residuo": Decimal(0), "unita": uom, "lotti": []})
        gruppo["residuo"] += Decimal(residuo)
        totale += Decimal(residuo)
        gruppo["lotti"].append({
            "lotto": lse, "fornitore": fornitore, "lotto_produttore": numero, "ricevuto": _giorno(ricevuto),
            "scadenza": _giorno(scadenza), "iniziale": _n(iniziale), "residuo": _n(residuo), "unita": uom,
            "anomalia": anomalia or None, "seminato_per": [v for v in (varieta or "").split(", ") if v],
        })
    ordinate = sorted(referenze.values(), key=lambda g: _fold(g["referenza"]))
    for g in ordinate:
        g["residuo"] = _n(g["residuo"])
    return {"totale_g": _n(totale), "lotti": len(lotti), "referenze": ordinate}


def _materiali(articoli: Sequence[Sequence[Any]]) -> dict:
    righe, possibili = [], []
    for codice, nome, uom, disponibile, ultimo in articoli:
        f = _fold(nome)
        set_possibili = None
        if uom == "UNIT" and ("vaschett" in f or "substrat" in f):
            set_possibili = Decimal(disponibile) // PEZZI_PER_SET if Decimal(disponibile) >= 0 else Decimal(0)
            possibili.append(set_possibili)
        righe.append({"codice": codice, "nome": nome, "giacenza": _n(disponibile), "unita": uom,
                      "ultimo_movimento": _giorno(ultimo),
                      "set_possibili": _n(set_possibili) if set_possibili is not None else None})
    return {"pezzi_per_set": int(PEZZI_PER_SET), "articoli": righe,
            "set_possibili": _n(min(possibili)) if possibili else None}


def _totale(semine: Sequence[dict]) -> Decimal:
    return sum((s["set"] for s in semine if s["set"] is not None), Decimal(0))


def _coltivazione(righe: Sequence[Sequence[Any]]) -> dict:
    semine = []
    for pid, codice, varieta, stato, avvio, atteso, uom, raccolto in righe:
        semine.append({"id": pid, "codice": codice or "senza codice", "varieta": varieta, "stato": stato,
                       "avvio": _giorno(avvio),
                       "set": Decimal(atteso) if atteso is not None and uom == "SET" else None,
                       "raccolto": Decimal(raccolto)})
    stadi = []
    for stadio in STADI:
        lista = [s for s in semine if s["stato"] == stadio]
        stadi.append({
            "stadio": stadio, "set": _n(_totale(lista)), "semine": len(lista),
            "elenco": [{"id": s["id"], "codice": s["codice"], "varieta": s["varieta"],
                        "set": _n(s["set"]) if s["set"] is not None else None, "avvio": s["avvio"],
                        "raccolto": _n(s["raccolto"]) if s["raccolto"] > 0 else None} for s in lista],
        })
    in_semina = [s for s in semine if s["stato"] in IN_SEMINA]
    per_varieta: dict[str, Decimal] = {}
    for s in in_semina:
        if s["set"] is not None:
            per_varieta[s["varieta"]] = per_varieta.get(s["varieta"], Decimal(0)) + s["set"]
    return {
        "in_semina": {"set": _n(_totale(in_semina)), "semine": len(in_semina)},
        "stadi": stadi,
        "per_varieta": [{"varieta": v, "set": _n(q)} for v, q in sorted(per_varieta.items(), key=lambda kv: _fold(kv[0]))],
        "senza_set": [s["id"] for s in in_semina if s["set"] is None],
    }


def componi(lotti: Sequence[Sequence[Any]], articoli: Sequence[Sequence[Any]], semine: Sequence[Sequence[Any]],
            adesso: datetime | None = None) -> dict:
    """Righe del database -> dati della pagina. Funzione pura: non legge ne' scrive nulla."""
    return {"aggiornato": (adesso or datetime.now(timezone.utc)).isoformat(), "semi": _semi(lotti),
            "materiali": _materiali(articoli), "coltivazione": _coltivazione(semine)}


def leggi(settings: PostgreSQLSettings) -> dict:
    with db_context._connect(settings) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(SQL_LOTTI)
            lotti = cur.fetchall()
            cur.execute(SQL_ARTICOLI)
            articoli = cur.fetchall()
            cur.execute(SQL_SEMINE)
            semine = cur.fetchall()
    return componi(lotti, articoli, semine)
