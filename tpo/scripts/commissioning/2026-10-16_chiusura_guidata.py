"""CHIUSURA GUIDATA delle semine raccolte per intero (16/10/2026).

Senza opzioni: SOLA LETTURA. Elenca le semine non chiuse con resa attesa compilata (in SET) e dice per ciascuna, sempre con
il codice di tracciabilita':
  - RACCOLTA PER INTERO (raccolti >= attesi): chiudibile se e' PRONTA_ALLA_RACCOLTA e non ha allocazioni
    PRODUZIONE_IN_CORSO attive; altrimenti dice perche' no;
  - IN CORSO: raccolti meno degli attesi (informativo);
  - semine con raccolte ma resa attesa NON compilata (informativo).
Stampa il comando pronto per chiudere tutte quelle chiudibili in una volta.

Con --chiudi SEM-... [SEM-...]: anteprima della chiusura di QUELLE semine; con --esegui le chiude davvero (transizione a
CHIUSA, esito "raccolta completa", una per volta, motivo con SOLO cio' che il sistema sa: raccolte registrate e quantita').
Non crea raccolte, movimenti, consegne, fatture; non tocca stock, ordini, grammi. Rifiuta (nulla scritto) una semina non
raccolta per intero, non PRONTA_ALLA_RACCOLTA, con allocazioni in corso, o con un evento successivo alla data di chiusura.
Idempotente (una semina gia' CHIUSA viene saltata). NON c'e' un comando per riaprire una semina chiusa: la chiusura va
considerata definitiva, quindi guarda l'anteprima.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-16_chiusura_guidata.py                       # elenco
  .venv/bin/python scripts/commissioning/2026-10-16_chiusura_guidata.py --chiudi SEM-000008    # anteprima
  .venv/bin/python scripts/commissioning/2026-10-16_chiusura_guidata.py --chiudi SEM-000008 --esegui
Opzioni: --chiusa-il "2026-10-16T09:00" (default adesso, ora di Canarie)   --esito "raccolta completa"
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
TZ = ZoneInfo("Atlantic/Canary")
ESITI = ["raccolta completa", "raccolta parziale con scarto", "scarto totale", "interruzione"]
PROV = '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED","final_outcome":"OWNER_AUTHORIZED"}'
SELF = "scripts/commissioning/2026-10-16_chiusura_guidata.py"

SQL = """
SELECT s.id, s.public_id, s.codice_tracciabilita, v.denominazione, s.stato::text, s.version, s.data_avvio,
       s.expected_useful_quantity, s.expected_useful_uom::text,
       COALESCE((SELECT SUM(rc.quantita) FROM tpo.raccolte rc WHERE rc.semina_id=s.id AND rc.unita_misura='SET'),0),
       (SELECT count(*) FROM tpo.allocazioni a JOIN tpo.allocazioni_produzione_in_corso aip
          ON aip.allocation_id=a.id WHERE aip.semina_id=s.id AND a.state='ATTIVA'),
       (SELECT max(e.effective_at) FROM tpo.semina_lifecycle_eventi e WHERE e.semina_id=s.id)
FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
WHERE s.stato<>'CHIUSA' ORDER BY v.denominazione, s.data_avvio, s.public_id"""
SQL_RACCOLTE = """SELECT r.public_id, r.data_raccolta, r.quantita, r.unita_misura::text
                  FROM tpo.raccolte r WHERE r.semina_id=%s ORDER BY r.data_raccolta, r.public_id"""


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def leggi(cur):
    cur.execute(SQL)
    semine = []
    for (pk, pid, codice, varieta, stato, version, avvio, atteso, uom, raccolto, in_corso, ultimo) in cur.fetchall():
        semine.append({"pk": pk, "id": pid, "codice": codice or "senza codice", "varieta": varieta, "stato": stato,
                       "version": version, "avvio": avvio, "atteso": None if atteso is None or uom != "SET" else Decimal(atteso),
                       "raccolto": Decimal(raccolto), "in_corso": in_corso, "ultimo": ultimo})
    return semine


def blocco(s) -> str | None:
    """Motivo per cui una semina raccolta per intero NON si puo' chiudere, None se chiudibile."""
    if s["stato"] != "PRONTA_ALLA_RACCOLTA":
        return f"e' {s['stato']}, non PRONTA_ALLA_RACCOLTA"
    if s["in_corso"]:
        return f"ha {s['in_corso']} allocazioni PRODUZIONE_IN_CORSO attive (da rilasciare prima)"
    return None


def completa(s) -> bool:
    return s["atteso"] is not None and s["atteso"] > 0 and s["raccolto"] >= s["atteso"]


def etichetta(s) -> str:
    return f"{s['id']} {s['codice']} {s['varieta']}"


def motivo(s, raccolte, oggi: datetime) -> str:
    parti = ", ".join(f"{r[0]} {_n(r[2])} {r[3]}" for r in raccolte) or "nessuna"
    return (f"Chiusura {s['id']} ({s['codice']}, {s['varieta']} avviata il {s['avvio']:%d/%m/%Y}) dichiarata da Matteo il "
            f"{oggi:%d/%m/%Y}: semina interamente raccolta secondo le raccolte registrate a sistema ({_n(s['raccolto'])} SET "
            f"raccolti su {_n(s['atteso'])} attesi: {parti}). Nessuna quantita' ulteriore viene registrata da questa chiusura.")


def comando(s, motivo_testo: str, when: datetime, esito: str) -> list[str]:
    chiave = f"chiusura-guidata-{s['id']}"
    return [RUN, "semina", "transition", "--semina", s["id"], "--expected-semina-version", str(s["version"]),
            "--target-state", "CHIUSA", "--effective-at", when.isoformat(), "--final-outcome", esito,
            "--provenance", PROV, "--actor", "matteo", "--reason", motivo_testo,
            "--correlation-id", chiave, "--idempotency-key", chiave, "--confirm"]


def elenco(conn, out) -> int:
    semine = leggi(conn.cursor())
    complete = [s for s in semine if completa(s)]
    chiudibili = [s for s in complete if blocco(s) is None]
    out("== SEMINE RACCOLTE PER INTERO (SOLA LETTURA, NULLA SCRITTO)")
    if not complete:
        out("   nessuna: tutte le semine non chiuse hanno ancora raccolto da fare.")
    for s in complete:
        b = blocco(s)
        out(f"   {etichetta(s)}  avviata {s['avvio']:%Y-%m-%d}  raccolti {_n(s['raccolto'])} su {_n(s['atteso'])} SET  "
            + ("-> chiudibile" if b is None else f"-> NON chiudibile: {b}"))
    parziali = [s for s in semine if s["atteso"] is not None and not completa(s) and s["raccolto"] > 0]
    if parziali:
        out("\nIN CORSO (raccolta in parte):")
        for s in parziali:
            out(f"   {etichetta(s)}  {s['stato']}  raccolti {_n(s['raccolto'])} su {_n(s['atteso'])} SET")
    senza = [s for s in semine if s["atteso"] is None and s["raccolto"] > 0]
    if senza:
        out("\nRACCOLTE MA RESA ATTESA NON COMPILATA (non le valuto):")
        for s in senza:
            out(f"   {etichetta(s)}  {s['stato']}  raccolti {_n(s['raccolto'])} SET")
    if chiudibili:
        codici = " ".join(s["id"] for s in chiudibili)
        out(f"\nPer vedere l'anteprima di tutte le chiudibili ({len(chiudibili)}):\n"
            f"   .venv/bin/python {SELF} --chiudi {codici}\n"
            "Per chiuderne solo alcune, tieni solo i codici che vuoi. La chiusura e' definitiva.")
    return 0


def chiudi(conn, codici, esito, when: datetime, esegui, out, runner) -> int:
    cur = conn.cursor()
    per_id = {s["id"]: s for s in leggi(cur)}
    piano = []
    for codice in codici:
        s = per_id.get(codice)
        if s is None:
            cur.execute("SELECT stato::text, codice_tracciabilita FROM tpo.semine WHERE public_id=%s", (codice,))
            row = cur.fetchone()
            if row and row[0] == "CHIUSA":
                out(f"{codice} {row[1] or ''}: gia' CHIUSA, salto.")
                continue
            out(f"RIFIUTATO, nulla scritto: {codice} inesistente.")
            return 2
        if s["atteso"] is None:
            out(f"RIFIUTATO, nulla scritto: {etichetta(s)} non ha la resa attesa compilata in SET: non posso dire che sia "
                "raccolta per intero.")
            return 2
        if not completa(s):
            out(f"RIFIUTATO, nulla scritto: {etichetta(s)} ha raccolto {_n(s['raccolto'])} SET su {_n(s['atteso'])} attesi: "
                "non e' raccolta per intero.")
            return 2
        b = blocco(s)
        if b:
            out(f"RIFIUTATO, nulla scritto: {etichetta(s)} {b}.")
            return 2
        if s["ultimo"] and when < s["ultimo"]:
            out(f"RIFIUTATO, nulla scritto: la chiusura {when:%Y-%m-%d %H:%M} precede l'ultimo evento di {etichetta(s)} "
                f"({s['ultimo']:%Y-%m-%d %H:%M}).")
            return 2
        cur.execute(SQL_RACCOLTE, (s["pk"],))
        raccolte = cur.fetchall()
        testo = motivo(s, raccolte, when)
        out(f"\n{etichetta(s)}: raccolti {_n(s['raccolto'])} su {_n(s['atteso'])} SET ({len(raccolte)} raccolte)\n"
            f"   -> verra' CHIUSA con esito \"{esito}\" il {when:%Y-%m-%d %H:%M}\n   Motivo: {testo}")
        piano.append((s, testo))
    if not piano:
        out("\nNiente da fare.")
        return 0
    if not esegui:
        out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui (la chiusura e' definitiva).")
        return 0
    for s, testo in piano:
        done = runner(comando(s, testo, when, esito))
        out(f"\n--- {etichetta(s)}\n" + ((done.stdout or "") + (done.stderr or "")).rstrip())
        if done.returncode != 0:
            out(f"STOP: comando fallito per {s['id']} (exit {done.returncode}); le precedenti sono gia' chiuse.")
            return 4
    out(f"\nFATTO: {len(piano)} semine chiuse.")
    return 0


def run(conn, codici=None, esito="raccolta completa", when: datetime | None = None, esegui=False, out=print,
        runner=lambda cmd: subprocess.run(cmd, capture_output=True, text=True)) -> int:
    when = when or datetime.now(TZ).replace(second=0, microsecond=0)
    if codici:
        return chiudi(conn, codici, esito, when, esegui, out, runner)
    return elenco(conn, out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chiudi", nargs="+", metavar="SEM-...", help="chiude queste semine (anteprima senza --esegui)")
    ap.add_argument("--esegui", action="store_true")
    ap.add_argument("--esito", default="raccolta completa", choices=ESITI)
    ap.add_argument("--chiusa-il", default="adesso", help='ISO 8601 oppure "adesso" (ora di Canarie)')
    a = ap.parse_args()
    when = (datetime.now(TZ).replace(second=0, microsecond=0) if a.chiusa_il == "adesso"
            else datetime.fromisoformat(a.chiusa_il))
    if when.tzinfo is None:
        when = when.replace(tzinfo=TZ)
    if a.esegui and not a.chiudi:
        raise SystemExit("STOP: --esegui serve con --chiudi SEM-... (prima guarda l'elenco).")
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"], autocommit=True)
    try:
        return run(conn, a.chiudi, a.esito, when, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
