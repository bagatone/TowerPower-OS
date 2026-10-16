"""SOLA LETTURA - PIANO SEMINE a SESSIONI: cosa seminare nei due giorni fissi della settimana e per chi (16/10/2026).

Richiesta di Matteo: invece di seminare un po' ogni giorno, si semina in due giorni (default mercoledi e domenica) e il
sistema dice, per ogni sessione, quali varieta' e quanti SET (con i grammi di seme) e per quali clienti.

La data ideale di semina di ogni riga e la quantita' da avviare le ha gia' calcolate il motore di pianificazione
(al netto di stock, semine in corso e buffer); qui si raggruppano. Regola: ogni riga va alla sessione PRECEDENTE alla sua
data ideale (si semina in anticipo, mai in ritardo). Se quella sessione e' gia' passata va alla prossima ed e' segnata
in ritardo. Restano FUORI dalle sessioni, elencati a parte per ordine: gli ORDINI SCADUTI (consegna gia' passata, ordine
ancora aperto: spesso residui da chiudere) e quelli DA VERIFICARE (piano in ritardo di oltre 7 giorni: una semina nuova non
rispetta piu' la consegna; coperti da giacenza o semine in corso? consegna da spostare?).

Non scrive nulla. Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-16_sessioni_semina.py
  .venv/bin/python scripts/commissioning/2026-10-16_sessioni_semina.py --sessioni 4
  .venv/bin/python scripts/commissioning/2026-10-16_sessioni_semina.py --giorni martedi venerdi
Opzioni: --sessioni N (quante sessioni mostrare, default 2)   --giorni G [G ...] (nomi dei giorni, default mercoledi domenica)
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

from src.tpo_core.diario_web import sessioni_semina as ss  # noqa: E402


def _giorni(nomi: list[str]) -> tuple[int, ...]:
    piatti = {n: i + 1 for i, n in enumerate(ss.NOMI_GIORNO)}
    risultato = []
    for nome in nomi:
        chiave = "".join(c for c in unicodedata.normalize("NFD", nome.lower()) if unicodedata.category(c) != "Mn").strip("'")
        if chiave not in piatti:
            raise SystemExit(f"STOP: giorno '{nome}' sconosciuto (usa: {', '.join(ss.NOMI_GIORNO)}).")
        risultato.append(piatti[chiave])
    return tuple(risultato)


def run(conn, giorni=ss.GIORNI_DEFAULT, n_sessioni: int = 2, oggi=None, out=print) -> int:
    from datetime import datetime
    oggi = oggi or datetime.now(ss.TZ).date()
    cur = conn.cursor()
    righe = ss.leggi_righe(cur)
    conn.rollback()
    for riga in ss.testo(ss.assegna(righe, oggi, giorni, n_sessioni)):
        out(riga)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sessioni", type=int, default=2)
    ap.add_argument("--giorni", nargs="+", default=["mercoledi", "domenica"])
    a = ap.parse_args()
    if a.sessioni < 1:
        raise SystemExit("STOP: --sessioni deve essere almeno 1.")
    giorni = _giorni(a.giorni)
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, giorni, a.sessioni)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
