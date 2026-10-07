"""Chiude semine GIA' RACCOLTE E VENDUTE (6/10/2026, dichiarazione di Matteo: SEM-000001 Cilantro, SEM-000002 Afila).

Per ogni semina: transizione a CHIUSA con esito "raccolta completa" (default). Il motivo riporta SOLO cio' che
il sistema sa (raccolte registrate, quantita', carico a magazzino) piu' la dichiarazione di Matteo; non
inventa quantita' per cio' che non e' registrato. Non crea raccolte, movimenti, consegne, fatture, e non
tocca stock, ordini, grammi registrati. Nessuna allocazione PRODUZIONE_IN_CORSO viene toccata (il controllo
la rifiuta se ne esiste una attiva).

Senza --esegui NON scrive nulla (anteprima). Idempotente (se gia' CHIUSA, salta).

Uso:
  .venv/bin/python scripts/commissioning/2026-10-06_chiudi_semine_raccolte.py            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-06_chiudi_semine_raccolte.py --esegui
  opzioni: --semine SEM-000001 SEM-000002   --esito "raccolta completa"
"""
import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
TZ = timezone(timedelta(hours=1))
ESITI = ["raccolta completa", "raccolta parziale con scarto", "scarto totale", "interruzione"]
DEFAULT_SEMINE = ("SEM-000001", "SEM-000002")
PROV = '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED","final_outcome":"OWNER_AUTHORIZED"}'


def read_semina(cur, public_id):
    cur.execute("""SELECT s.id, s.stato::text, s.version, s.codice_tracciabilita, v.denominazione, s.data_avvio,
                          s.quantita_seme,
                          (SELECT max(e.effective_at) FROM tpo.semina_lifecycle_eventi e WHERE e.semina_id=s.id),
                          (SELECT count(*) FROM tpo.allocazioni a JOIN tpo.allocazioni_produzione_in_corso aip
                             ON aip.allocation_id=a.id WHERE aip.semina_id=s.id AND a.state='ATTIVA')
                   FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id WHERE s.public_id=%s""", (public_id,))
    return cur.fetchone()


def read_raccolte(cur, semina_pk):
    cur.execute("""SELECT r.public_id, r.data_raccolta, r.quantita, r.unita_misura::text,
                          COALESCE((SELECT SUM(m.quantita) FROM tpo.movimenti_magazzino m
                                    WHERE m.raccolta_id=r.id AND m.tipo='CARICO' AND m.unita_misura=r.unita_misura),0)
                   FROM tpo.raccolte r WHERE r.semina_id=%s ORDER BY r.data_raccolta, r.public_id""", (semina_pk,))
    return cur.fetchall()


def reason_for(public_id, varieta, avvio, raccolte) -> str:
    if raccolte:
        parts = ", ".join(f"{r[0]} {r[2].normalize():f} {r[3]}" for r in raccolte)
        registered = f"Raccolte registrate a sistema: {parts}."
    else:
        registered = "Nessuna raccolta registrata a sistema."
    return (f"Chiusura {public_id} ({varieta} {avvio:%d/%m/%Y}) dichiarata da Matteo il 6/10/2026: semina gia' "
            f"interamente raccolta e venduta (vendite non registrate). {registered} "
            "Nessuna quantita' ulteriore viene registrata da questa chiusura.")


def build_command(public_id, version, when, esito, reason):
    return [RUN, "semina", "transition", "--semina", public_id, "--expected-semina-version", str(version),
            "--target-state", "CHIUSA", "--effective-at", when.isoformat(), "--final-outcome", esito,
            "--provenance", PROV, "--actor", "matteo", "--reason", reason,
            "--correlation-id", f"chiusura-2026-10-06-{public_id}",
            "--idempotency-key", f"chiusura-2026-10-06-{public_id}", "--confirm"]


def run(conn, semine, esito, when, esegui, out=print) -> int:
    cur = conn.cursor()
    plan = []
    for public_id in semine:
        row = read_semina(cur, public_id)
        if not row:
            out(f"STOP: {public_id} inesistente.")
            return 1
        pk, stato, version, codice, varieta, avvio, grammi, ultimo, in_corso = row
        raccolte = read_raccolte(cur, pk)
        out(f"\n{public_id} {codice} {varieta}: stato {stato}, versione {version}, avvio {avvio:%Y-%m-%d}, {grammi} g")
        for r in raccolte:
            out(f"   raccolta {r[0]} del {r[1]:%Y-%m-%d %H:%M}: {r[2]} {r[3]}, caricata a magazzino {r[4]}")
        if not raccolte:
            out("   nessuna raccolta registrata")
        if stato == "CHIUSA":
            out("   gia' CHIUSA: salto.")
            continue
        if stato != "PRONTA_ALLA_RACCOLTA":
            out(f"STOP: {public_id} e' {stato}, non PRONTA_ALLA_RACCOLTA: non la chiudo come 'gia' raccolta'.")
            return 1
        if in_corso:
            out(f"STOP: {public_id} ha {in_corso} allocazioni PRODUZIONE_IN_CORSO attive: da rilasciare prima.")
            return 1
        if ultimo and when < ultimo:
            out(f"STOP: chiusura {when} precede l'ultimo evento {ultimo}.")
            return 1
        reason = reason_for(public_id, varieta, avvio, raccolte)
        out(f"   -> verra' CHIUSA con esito \"{esito}\" alle {when:%Y-%m-%d %H:%M}\n   Motivo: {reason}")
        plan.append((public_id, version, reason))
    if not esegui:
        out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        return 0
    for public_id, version, reason in plan:
        done = subprocess.run(build_command(public_id, version, when, esito, reason), capture_output=True, text=True)
        out(f"\n--- {public_id}\n" + ((done.stdout or "") + (done.stderr or "")).rstrip())
        if done.returncode != 0:
            out(f"STOP: comando fallito per {public_id} (exit {done.returncode}).")
            return 4
    out("\nFATTO." if plan else "\nNiente da fare.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true")
    ap.add_argument("--semine", nargs="+", default=list(DEFAULT_SEMINE))
    ap.add_argument("--esito", default="raccolta completa", choices=ESITI)
    ap.add_argument("--chiusa-il", default="adesso", help='ISO 8601 oppure "adesso"')
    a = ap.parse_args()
    when = (datetime.now(TZ).replace(second=0, microsecond=0) if a.chiusa_il == "adesso"
            else datetime.fromisoformat(a.chiusa_il))
    if when.tzinfo is None:
        when = when.replace(tzinfo=TZ)
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"],
                           autocommit=True)
    try:
        return run(conn, a.semine, a.esito, when, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
