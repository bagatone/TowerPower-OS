"""Toglie la nota di ANOMALIA dai lotti di seme Hyfarm LSE-000016 (Col Roja) e LSE-000017 (Girasoli) - 12/10/2026.

Perche': `tpo semina commission` rifiuta ogni lotto con un'anomalia registrata ("LSE con anomalia non eleggibile"), quindi
Cavolo rosso e Girasole non si possono seminare nel sistema. Lo stesso e' successo il 2/10 con i lotti Intersemillas: la
nota era solo informativa (seme dichiarato a voce, senza etichetta) e Matteo ha autorizzato a toglierla.

NON TOGLIERE UNA NOTA CHE DICE UN PROBLEMA VERO DEL SEME (muffa, scadenza, contaminazione...). Per questo lo script, prima
di tutto, STAMPA il testo esatto di ciascuna anomalia: leggilo, e solo se e' una nota informativa lancia --esegui.

Cosa fa con --esegui (una transazione, tutto o niente): per ogni lotto che ha ancora l'anomalia
  - azzera la colonna anomalia, version +1, updated_by = matteo;
  - scrive un evento di audit (LOTTO_SEME, UPDATE) con il TESTO ORIGINALE nel before_data e nel motivo.
Nulla altro cambia (quantita', lotto, scadenza restano come sono). Rilanciabile: un lotto senza anomalia viene saltato.

Senza --esegui NON scrive nulla (anteprima).

COMANDO CORRETTIVO (rimette la nota esattamente com'era, leggendola dall'audit):
  .venv/bin/python scripts/commissioning/2026-10-12_anomalia_lotti.py --ripristina --esegui

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-12_anomalia_lotti.py                 # anteprima: mostra i testi
  .venv/bin/python scripts/commissioning/2026-10-12_anomalia_lotti.py --esegui
  Opzioni: --lotti LSE-000016 LSE-000017 (default)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

ACTOR = "matteo"
LOTTI_DEFAULT = ["LSE-000016", "LSE-000017"]
TAG = "anomalia-lotti-2026-10-12"
SELF = "scripts/commissioning/2026-10-12_anomalia_lotti.py"


def _lot(cur, public_id):
    cur.execute("""SELECT l.id, l.version, l.anomalia, l.quantita_residua, s.fornitore, s.referenza_commerciale
                   FROM tpo.lotti_seme l JOIN tpo.sementi s ON s.id=l.semente_id WHERE l.public_id=%s""", (public_id,))
    return cur.fetchone()


def _audit(cur, public_id, before, after, reason, correlation):
    from psycopg.types.json import Jsonb
    cur.execute("""INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,before_data,after_data,
                    correlation_id,provenance)
                   VALUES (now(),%s,'LOTTO_SEME',%s,'UPDATE',%s,%s,%s,%s,%s)""",
                (ACTOR, public_id, reason, Jsonb(before), Jsonb(after), correlation,
                 json.dumps({"boundary": TAG}, sort_keys=True)))


def rimuovi(conn, lotti, esegui, out=print) -> int:
    cur = conn.cursor()
    out(f"== ANOMALIA LOTTI SEME -- {'ESECUZIONE' if esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    da_fare = []
    for pid in lotti:
        row = _lot(cur, pid)
        if not row:
            out(f"STOP: lotto {pid} inesistente.")
            return 1
        _, version, anomalia, residuo, fornitore, referenza = row
        out(f"\n{pid} ({fornitore} / {referenza}), residuo {residuo} g, versione {version}")
        if anomalia is None:
            out("  nessuna anomalia registrata: salto.")
            continue
        out(f"  ANOMALIA REGISTRATA (testo esatto): {anomalia!r}")
        da_fare.append((pid, row))
    if not da_fare:
        out("\nNiente da fare.")
        return 0
    if not esegui:
        out("\nLeggi i testi qui sopra. Se sono solo note informative, rilancia con --esegui; se descrivono un problema "
            "vero del seme NON procedere e dimmelo.")
        out(f"COMANDO CORRETTIVO (dopo l'esecuzione): .venv/bin/python {SELF} --ripristina --esegui")
        return 0
    for pid, (lot_id, version, anomalia, *_r) in da_fare:
        cur.execute("""UPDATE tpo.lotti_seme SET anomalia=NULL, updated_at=now(), updated_by=%s, version=version+1
                       WHERE id=%s AND version=%s AND anomalia IS NOT NULL""", (ACTOR, lot_id, version))
        if cur.rowcount != 1:
            conn.rollback()
            out(f"STOP: {pid} e' cambiato nel frattempo: nulla scritto, rilancia.")
            return 1
        _audit(cur, pid, {"anomalia": anomalia, "version": int(version)}, {"anomalia": None, "version": int(version) + 1},
               f"Rimossa la nota di anomalia (autorizzata da Matteo il 12/10/2026) per poter seminare: testo originale: "
               f"{anomalia}", f"{TAG}-{pid}")
        out(f"  {pid}: anomalia rimossa (versione {int(version) + 1}); testo originale conservato nell'audit.")
    conn.commit()
    out(f"\nFATTO. COMANDO CORRETTIVO: .venv/bin/python {SELF} --ripristina --esegui")
    return 0


def ripristina(conn, lotti, esegui, out=print) -> int:
    cur = conn.cursor()
    out(f"== RIPRISTINO ANOMALIA -- {'ESECUZIONE' if esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    fatti = []
    for pid in lotti:
        row = _lot(cur, pid)
        if not row:
            out(f"STOP: lotto {pid} inesistente.")
            return 1
        lot_id, version, anomalia, *_ = row
        cur.execute("""SELECT before_data->>'anomalia' FROM tpo.audit_eventi
                       WHERE entity_type='LOTTO_SEME' AND entity_public_id=%s AND correlation_id=%s
                       ORDER BY id DESC LIMIT 1""", (pid, f"{TAG}-{pid}"))
        old = cur.fetchone()
        if anomalia is not None:
            out(f"{pid}: ha gia' un'anomalia: salto.")
        elif not old or old[0] is None:
            out(f"{pid}: non risulta nessuna rimozione fatta da questo script: salto.")
        else:
            out(f"{pid}: rimetto {old[0]!r}")
            fatti.append((pid, lot_id, version, old[0]))
    if not esegui or not fatti:
        out("\n(anteprima o niente da fare: nulla scritto)")
        return 0
    for pid, lot_id, version, old in fatti:
        cur.execute("""UPDATE tpo.lotti_seme SET anomalia=%s, updated_at=now(), updated_by=%s, version=version+1
                       WHERE id=%s AND version=%s AND anomalia IS NULL""", (old, ACTOR, lot_id, version))
        if cur.rowcount != 1:
            conn.rollback()
            out(f"STOP: {pid} e' cambiato nel frattempo: nulla scritto.")
            return 1
        _audit(cur, pid, {"anomalia": None, "version": int(version)}, {"anomalia": old, "version": int(version) + 1},
               "Ripristinata la nota di anomalia originale (correzione richiesta da Matteo)", f"{TAG}-ripristino-{pid}-v{int(version)}")
    conn.commit()
    out("FATTO: anomalie ripristinate.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    ap.add_argument("--ripristina", action="store_true", help="rimette la nota originale (comando correttivo)")
    ap.add_argument("--lotti", nargs="+", default=LOTTI_DEFAULT)
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return (ripristina if a.ripristina else rimuovi)(conn, a.lotti, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
