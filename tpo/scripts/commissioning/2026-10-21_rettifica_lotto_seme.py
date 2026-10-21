"""RETTIFICA (solo in DIMINUZIONE) del residuo di un LOTTO DI SEME (21/10/2026, richiesta di Matteo: il sacco di Cilantro
LSE-000013 e' finito fisicamente, ma il sistema ne mostrava ancora 116 g).

Il residuo di un lotto cala solo con le semine; quando il sacco si esaurisce o si perde seme senza una semina, il
residuo del sistema resta piu' alto della realta'. Questo comando lo porta al valore REALE dichiarato da Matteo:

  .venv/bin/python scripts/commissioning/2026-10-21_rettifica_lotto_seme.py LSE-000013 --residuo 0 \\
      --motivo "Sacco finito fisicamente: ultimi grammi usati con la semina del 21/10/2026"
  ... --esegui    per scrivere davvero (senza: solo ANTEPRIMA, non scrive nulla)

Cosa fa (una transazione, tutto o niente): aggiorna `lotti_seme.quantita_residua` (version +1, updated_by = matteo) e
scrive un evento di audit LOTTO_SEME con residuo prima/dopo, differenza e MOTIVO. Non tocca semine, protocolli,
movimenti, stock di raccolti.

Rifiuta (nulla scritto): lotto inesistente; residuo dichiarato maggiore o uguale a quello a sistema (si rettifica solo
verso il basso: non si inventa seme); residuo negativo; motivo mancante; lotto cambiato nel frattempo.

COMANDO CORRETTIVO (stampato a fine esecuzione): rimette il residuo a quello di prima (`--ripristina`, legge l'ultimo
audit di questo script per quel lotto).
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

ACTOR = "matteo"
TAG = "rettifica-lotto-seme-2026-10-21"
SELF = "scripts/commissioning/2026-10-21_rettifica_lotto_seme.py"


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def _lot(cur, public_id):
    cur.execute("""SELECT l.id, l.version, l.quantita_residua, l.quantita_iniziale, l.unita_misura::text,
                          s.fornitore, s.referenza_commerciale
                   FROM tpo.lotti_seme l JOIN tpo.sementi s ON s.id=l.semente_id WHERE l.public_id=%s FOR UPDATE OF l""",
                (public_id,))
    return cur.fetchone()


def _audit(cur, public_id, before, after, reason, correlation):
    from psycopg.types.json import Jsonb
    cur.execute("""INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,before_data,after_data,
                    correlation_id,provenance)
                   VALUES (now(),%s,'LOTTO_SEME',%s,'UPDATE',%s,%s,%s,%s,%s)""",
                (ACTOR, public_id, reason, Jsonb(before), Jsonb(after), correlation,
                 json.dumps({"boundary": TAG}, sort_keys=True)))


def rettifica(conn, lotto: str, residuo: Decimal, motivo: str, esegui: bool, out=print) -> int:
    cur = conn.cursor()
    try:
        if not motivo or not motivo.strip():
            out("RIFIUTATO, nulla scritto: serve un --motivo.")
            return 2
        if residuo < 0:
            out("RIFIUTATO, nulla scritto: il residuo non puo' essere negativo.")
            return 2
        row = _lot(cur, lotto)
        if not row:
            out(f"RIFIUTATO, nulla scritto: lotto {lotto} inesistente.")
            return 2
        lot_id, version, attuale, iniziale, unita, fornitore, referenza = row
        out(f"== RETTIFICA LOTTO SEME {lotto} -- {'ESECUZIONE' if esegui else 'ANTEPRIMA (nulla viene scritto)'}")
        out(f"{lotto} ({fornitore} / {referenza}): iniziale {_n(iniziale)} {unita}, residuo a sistema {_n(attuale)} {unita}, "
            f"versione {version}")
        if residuo >= attuale:
            out(f"RIFIUTATO, nulla scritto: {_n(residuo)} non e' inferiore a quello a sistema ({_n(attuale)}): "
                "rettifico solo verso il basso, non invento seme.")
            return 2
        diff = attuale - residuo
        out(f"Residuo: {_n(attuale)} -> {_n(residuo)} {unita} (togliamo {_n(diff)} {unita} che fisicamente non ci sono)")
        out(f"Motivo registrato: {motivo}")
        if not esegui:
            conn.rollback()
            out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
            return 0
        cur.execute("""UPDATE tpo.lotti_seme SET quantita_residua=%s, updated_at=now(), updated_by=%s, version=version+1
                       WHERE id=%s AND version=%s AND quantita_residua=%s""", (residuo, ACTOR, lot_id, version, attuale))
        if cur.rowcount != 1:
            conn.rollback()
            out("STOP: il lotto e' cambiato nel frattempo: nulla scritto, rilancia.")
            return 1
        _audit(cur, lotto, {"quantita_residua": _n(attuale), "version": int(version), "unita": unita},
               {"quantita_residua": _n(residuo), "version": int(version) + 1, "unita": unita, "differenza": _n(diff)},
               f"Rettifica del residuo (dichiarata da Matteo): {motivo}", f"{TAG}-{lotto}-v{int(version)}")
        conn.commit()
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: {lotto} residuo {_n(residuo)} {unita} (versione {int(version) + 1}); prima {_n(attuale)}.")
    out("\n== COMANDO CORRETTIVO (rimette il residuo di prima):")
    out(f"   .venv/bin/python {SELF} {lotto} --ripristina --esegui")
    return 0


def ripristina(conn, lotto: str, esegui: bool, out=print) -> int:
    cur = conn.cursor()
    try:
        row = _lot(cur, lotto)
        if not row:
            out(f"RIFIUTATO, nulla scritto: lotto {lotto} inesistente.")
            return 2
        lot_id, version, attuale, *_ = row
        cur.execute("""SELECT before_data->>'quantita_residua', after_data->>'quantita_residua'
                       FROM tpo.audit_eventi WHERE entity_type='LOTTO_SEME' AND entity_public_id=%s
                         AND correlation_id LIKE %s ORDER BY id DESC LIMIT 1""", (lotto, f"{TAG}-{lotto}-v%"))
        ultimo = cur.fetchone()
        if not ultimo:
            out(f"RIFIUTATO, nulla scritto: nessuna rettifica di questo script su {lotto}.")
            return 2
        prima, dopo = Decimal(ultimo[0]), Decimal(ultimo[1])
        if attuale != dopo:
            out(f"RIFIUTATO, nulla scritto: il residuo ora ({_n(attuale)}) non e' quello lasciato dalla rettifica "
                f"({_n(dopo)}): nel frattempo e' cambiato, non lo tocco.")
            return 2
        out(f"== RIPRISTINO {lotto}: {_n(attuale)} -> {_n(prima)} ({'ESECUZIONE' if esegui else 'ANTEPRIMA'})")
        if not esegui:
            conn.rollback()
            out("ANTEPRIMA: nulla scritto.")
            return 0
        cur.execute("""UPDATE tpo.lotti_seme SET quantita_residua=%s, updated_at=now(), updated_by=%s, version=version+1
                       WHERE id=%s AND version=%s""", (prima, ACTOR, lot_id, version))
        if cur.rowcount != 1:
            conn.rollback()
            out("STOP: il lotto e' cambiato nel frattempo: nulla scritto.")
            return 1
        _audit(cur, lotto, {"quantita_residua": _n(attuale), "version": int(version)},
               {"quantita_residua": _n(prima), "version": int(version) + 1},
               "Ripristinato il residuo precedente (correzione richiesta da Matteo)",
               f"{TAG}-ripristino-{lotto}-v{int(version)}")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"FATTO: {lotto} residuo ripristinato a {_n(prima)}.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lotto", help="es. LSE-000013")
    ap.add_argument("--residuo", help="residuo REALE in grammi (solo inferiore a quello a sistema)")
    ap.add_argument("--motivo")
    ap.add_argument("--ripristina", action="store_true", help="rimette il residuo di prima (comando correttivo)")
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    if not a.ripristina:
        if a.residuo is None or not a.motivo:
            print("STOP: servono --residuo e --motivo (oppure --ripristina).", file=sys.stderr)
            return 1
        try:
            residuo = Decimal(a.residuo.replace(",", "."))
        except InvalidOperation:
            print(f"STOP: residuo '{a.residuo}' non valido.", file=sys.stderr)
            return 1
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        if a.ripristina:
            return ripristina(conn, a.lotto, a.esegui)
        return rettifica(conn, a.lotto, residuo, a.motivo, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
