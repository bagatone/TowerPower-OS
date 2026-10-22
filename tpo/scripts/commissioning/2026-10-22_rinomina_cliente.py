"""RINOMINA un CLIENTE (22/10/2026, richiesta di Matteo: il ristorante si chiama "Salvaje", ma il cliente CLI-000004 era
stato registrato con il refuso "Selvaje", e per lo stesso ristorante esiste anche il doppione CLI-000014 "Salvaje").

Cambia SOLO il nome (`clienti.denominazione`): CLI-..., ordini, consegne, programmi, pagamenti e bolle gia' registrati
restano esattamente come sono, perche' puntano al cliente per id e non per nome. Le bolle PDF nuove prendono il nuovo nome
e la sottocartella di ~/Desktop/bolle col nome nuovo; quelle gia' generate restano com'erano (si rifanno a parte).

  .venv/bin/python scripts/commissioning/2026-10-22_rinomina_cliente.py CLI-000014 "Salvaje (doppione archiviato)" \\
      --motivo "Doppione di CLI-000004: stesso ristorante, tenuto l'altro"
  .venv/bin/python scripts/commissioning/2026-10-22_rinomina_cliente.py CLI-000004 "Salvaje" \\
      --motivo "Refuso: il ristorante si chiama Salvaje, non Selvaje"
  ... --esegui    per scrivere davvero (senza: solo ANTEPRIMA, non scrive nulla)

Cosa fa con --esegui (una transazione, tutto o niente): aggiorna `clienti.denominazione` (version +1, updated_by = matteo) e
scrive un evento di audit CLIENTE con nome prima/dopo e MOTIVO.

Rifiuta (nulla scritto): cliente inesistente; nome vuoto o uguale a quello di adesso; motivo mancante; un ALTRO cliente
con lo stesso nome (senza distinzione di maiuscole): prima si rinomina quello, oppure --anche-se-duplicato; cliente
cambiato nel frattempo.

COMANDO CORRETTIVO (stampato a fine esecuzione): `--ripristina` rimette il nome di prima (legge l'ultimo audit di questo
script per quel cliente; si rifiuta se il nome nel frattempo e' cambiato ancora).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

ACTOR = "matteo"
TAG = "rinomina-cliente-2026-10-22"
SELF = "scripts/commissioning/2026-10-22_rinomina_cliente.py"


def _cliente(cur, public_id):
    cur.execute("SELECT id, version, denominazione FROM tpo.clienti WHERE public_id=%s FOR UPDATE", (public_id,))
    return cur.fetchone()


def _audit(cur, public_id, before, after, reason, correlation):
    from psycopg.types.json import Jsonb
    cur.execute("""INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,before_data,after_data,
                    correlation_id,provenance)
                   VALUES (now(),%s,'CLIENTE',%s,'UPDATE',%s,%s,%s,%s,%s)""",
                (ACTOR, public_id, reason, Jsonb(before), Jsonb(after), correlation,
                 json.dumps({"boundary": TAG}, sort_keys=True)))


def rinomina(conn, cliente: str, nuovo: str, motivo: str, esegui: bool, anche_se_duplicato: bool = False,
             out=print) -> int:
    cur = conn.cursor()
    try:
        nuovo = (nuovo or "").strip()
        if not nuovo:
            out("RIFIUTATO, nulla scritto: il nuovo nome non puo' essere vuoto.")
            return 2
        if not motivo or not motivo.strip():
            out("RIFIUTATO, nulla scritto: serve un --motivo.")
            return 2
        row = _cliente(cur, cliente)
        if not row:
            out(f"RIFIUTATO, nulla scritto: cliente {cliente} inesistente.")
            return 2
        cid, version, attuale = row
        out(f"== RINOMINA CLIENTE {cliente} -- {'ESECUZIONE' if esegui else 'ANTEPRIMA (nulla viene scritto)'}")
        out(f"{cliente}: '{attuale}' (versione {version})")
        if nuovo == attuale:
            out(f"RIFIUTATO, nulla scritto: il nome e' gia' '{attuale}'.")
            return 2
        cur.execute("SELECT public_id, denominazione FROM tpo.clienti WHERE lower(btrim(denominazione))=lower(%s) AND id<>%s",
                    (nuovo, cid))
        altri = cur.fetchall()
        if altri and not anche_se_duplicato:
            elenco = ", ".join(f"{p} '{n}'" for p, n in altri)
            out(f"RIFIUTATO, nulla scritto: esiste gia' un altro cliente con questo nome ({elenco}). Rinomina prima "
                "quello (nome diverso), oppure aggiungi --anche-se-duplicato.")
            return 2
        out(f"Nome: '{attuale}' -> '{nuovo}'")
        out("Cambia solo il nome: ordini, consegne, programmi, pagamenti e bolle gia' registrati restano com'erano.")
        out(f"Motivo registrato: {motivo}")
        if not esegui:
            conn.rollback()
            out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
            return 0
        cur.execute("""UPDATE tpo.clienti SET denominazione=%s, updated_at=now(), updated_by=%s, version=version+1
                       WHERE id=%s AND version=%s AND denominazione=%s""", (nuovo, ACTOR, cid, version, attuale))
        if cur.rowcount != 1:
            conn.rollback()
            out("STOP: il cliente e' cambiato nel frattempo: nulla scritto, rilancia.")
            return 1
        _audit(cur, cliente, {"denominazione": attuale, "version": int(version)},
               {"denominazione": nuovo, "version": int(version) + 1},
               f"Cliente rinominato (dichiarato da Matteo): {motivo}", f"{TAG}-{cliente}-v{int(version)}")
        conn.commit()
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: {cliente} ora si chiama '{nuovo}' (versione {int(version) + 1}); prima '{attuale}'.")
    out("\n== COMANDO CORRETTIVO (rimette il nome di prima):")
    out(f"   .venv/bin/python {SELF} {cliente} --ripristina --esegui")
    return 0


def ripristina(conn, cliente: str, esegui: bool, out=print) -> int:
    cur = conn.cursor()
    try:
        row = _cliente(cur, cliente)
        if not row:
            out(f"RIFIUTATO, nulla scritto: cliente {cliente} inesistente.")
            return 2
        cid, version, attuale = row
        cur.execute("""SELECT before_data->>'denominazione', after_data->>'denominazione'
                       FROM tpo.audit_eventi WHERE entity_type='CLIENTE' AND entity_public_id=%s
                         AND correlation_id LIKE %s ORDER BY id DESC LIMIT 1""", (cliente, f"{TAG}-{cliente}-v%"))
        ultimo = cur.fetchone()
        if not ultimo:
            out(f"RIFIUTATO, nulla scritto: nessuna rinomina di questo script su {cliente}.")
            return 2
        prima, dopo = ultimo
        if attuale != dopo:
            out(f"RIFIUTATO, nulla scritto: il nome ora ('{attuale}') non e' quello lasciato dalla rinomina ('{dopo}'): "
                "nel frattempo e' cambiato, non lo tocco.")
            return 2
        out(f"== RIPRISTINO {cliente}: '{attuale}' -> '{prima}' ({'ESECUZIONE' if esegui else 'ANTEPRIMA'})")
        if not esegui:
            conn.rollback()
            out("ANTEPRIMA: nulla scritto.")
            return 0
        cur.execute("""UPDATE tpo.clienti SET denominazione=%s, updated_at=now(), updated_by=%s, version=version+1
                       WHERE id=%s AND version=%s""", (prima, ACTOR, cid, version))
        if cur.rowcount != 1:
            conn.rollback()
            out("STOP: il cliente e' cambiato nel frattempo: nulla scritto.")
            return 1
        _audit(cur, cliente, {"denominazione": attuale, "version": int(version)},
               {"denominazione": prima, "version": int(version) + 1},
               "Ripristinato il nome precedente (correzione richiesta da Matteo)", f"{TAG}-ripristino-{cliente}-v{int(version)}")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"FATTO: {cliente} ripristinato a '{prima}'.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cliente", help="es. CLI-000004")
    ap.add_argument("nome", nargs="?", help="il nuovo nome (non serve con --ripristina)")
    ap.add_argument("--motivo")
    ap.add_argument("--anche-se-duplicato", action="store_true", help="permette un nome uguale a quello di un altro cliente")
    ap.add_argument("--ripristina", action="store_true", help="rimette il nome di prima (comando correttivo)")
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    if not a.ripristina and (not a.nome or not a.motivo):
        print("STOP: servono il nuovo nome e --motivo (oppure --ripristina).", file=sys.stderr)
        return 1
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        if a.ripristina:
            return ripristina(conn, a.cliente, a.esegui)
        return rinomina(conn, a.cliente, a.nome, a.motivo, a.esegui, a.anche_se_duplicato)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
