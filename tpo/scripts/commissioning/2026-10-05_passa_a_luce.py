"""Porta a LUCE (stato fisico dichiarato da Matteo il 5/10/2026) le semine di:
    Rabano 3 SET, Rucola 1 SET, Amaranto 1 SET     ("queste varieta' passano a luce oggi")

Per ogni varieta' lo script cerca le semine AVVIATA/GERMINAZIONE, calcola i SET di ciascuna
(grammi di seme / grammi per SET del protocollo della semina) e sceglie da solo SOLO se
esiste una sola combinazione che somma esattamente i SET dichiarati. Se e' ambigua (o i SET
non sono calcolabili) si ferma, elenca le candidate e chiede --semina SEM-... esplicito.

Passaggi: GERMINAZIONE alla data di avvio (se ancora AVVIATA; passaggio amministrativo, come le
altre semine) e LUCE all'istante indicato (default: adesso, orario non osservato ma registrato
alla conferma). CRESCITA NON viene registrata: LUCE e CRESCITA sono lo stesso processo
(indoor/outdoor, regola di Matteo 5/10/2026).

Senza --esegui NON scrive nulla (anteprima). Idempotente.

Uso:
  .venv/bin/python scripts/commissioning/2026-10-05_passa_a_luce.py                  # anteprima
  .venv/bin/python scripts/commissioning/2026-10-05_passa_a_luce.py --esegui
  ... --semina SEM-000016 --semina SEM-000018 ...                                   # scelta esplicita
  ... --varieta "Rabano:3" --varieta "Rucola:1" ...                                 # altre quantita'
"""
import argparse
import itertools
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402
import psycopg  # noqa: E402

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
TZ = timezone(timedelta(hours=1))
TAG = "2026-10-05-luce"
PROV = '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED"}'
DEFAULT = ["Rabano:3", "Rucola:1", "Amaranto:1"]


class Stop(Exception):
    pass


def norm(t):
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c)).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true")
    ap.add_argument("--varieta", action="append", help='"Nome:SET", ripetibile')
    ap.add_argument("--semina", action="append", default=[], help="SEM-... esplicita, ripetibile")
    ap.add_argument("--accetta-differenza", action="store_true",
                    help="procede anche se i SET calcolati dai grammi != SET dichiarati (solo per semine scelte "
                         "con --semina; il cambio di stadio non modifica quantita' ne' grammi registrati)")
    ap.add_argument("--luce-il", default="adesso", help='ISO 8601 oppure "adesso"')
    a = ap.parse_args()
    luce = (datetime.now(TZ).replace(second=0, microsecond=0) if a.luce_il == "adesso"
            else datetime.fromisoformat(a.luce_il))
    if luce.tzinfo is None:
        luce = luce.replace(tzinfo=TZ)
    dichiarate = {}
    for item in (a.varieta or DEFAULT):
        nome, n = item.rsplit(":", 1)
        dichiarate[norm(nome)] = Decimal(n)

    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"],
                           connect_timeout=p["connect_timeout"], autocommit=True)
    cur = conn.cursor()
    print(f"== LUCE {luce:%Y-%m-%d %H:%M} -- {'ESECUZIONE' if a.esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    try:
        cur.execute("SELECT denominazione FROM tpo.varieta")
        nomi = {norm(r[0]): r[0] for r in cur.fetchall()}
        scelte = []  # (semina, nome varieta')
        for chiave, richiesti in dichiarate.items():
            if chiave not in nomi:
                raise Stop(f"varieta' '{chiave}' sconosciuta; esistenti: {', '.join(sorted(nomi.values()))}")
            nome = nomi[chiave]
            cur.execute("""SELECT s.public_id, s.codice_tracciabilita, s.stato::text, s.data_avvio, s.version,
                                  s.quantita_seme, pv.grammi_seme_per_set
                           FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
                           LEFT JOIN tpo.protocollo_versioni pv ON pv.id=s.protocollo_versione_id
                           WHERE v.denominazione=%s AND s.stato IN ('AVVIATA','GERMINAZIONE')
                           ORDER BY s.data_avvio, s.public_id""", (nome,))
            cand = []
            for pid, codice, stato, avvio, version, grammi, gps in cur.fetchall():
                sets = (Decimal(grammi) / Decimal(gps)) if gps else None
                cand.append({"id": pid, "codice": codice, "stato": stato, "avvio": avvio, "version": version,
                             "grammi": grammi, "sets": sets})
            print(f"\n=== {nome}: dichiarati {richiesti} SET ===")
            for c in cand:
                print(f"  {c['id']} {c['codice']} {c['stato']} avvio {c['avvio']:%Y-%m-%d} "
                      f"{c['grammi']} g = {('%s SET' % c['sets'].normalize()) if c['sets'] is not None else 'SET ?'}")
            esplicite = [c for c in cand if c["id"] in a.semina]
            if esplicite:
                scelta = esplicite
            else:
                if any(c["sets"] is None for c in cand):
                    raise Stop(f"{nome}: SET non calcolabili; indica --semina SEM-... esplicita.")
                combos = [co for r in range(1, len(cand) + 1) for co in itertools.combinations(cand, r)
                          if sum(c["sets"] for c in co) == richiesti]
                if len(combos) != 1:
                    raise Stop(f"{nome}: {len(combos)} combinazioni di semine fanno {richiesti} SET; "
                               "indica --semina SEM-... esplicita (non scelgo io).")
                scelta = list(combos[0])
            tot = sum((c["sets"] for c in scelta if c["sets"] is not None), Decimal(0))
            if all(c["sets"] is not None for c in scelta) and tot != richiesti:
                if not (a.accetta_differenza and esplicite):
                    raise Stop(f"{nome}: le semine scelte fanno {tot} SET (da grammi di seme), dichiarati {richiesti}. "
                               "Se e' voluto: --semina SEM-... --accetta-differenza (nessun dato registrato viene cambiato).")
                print(f"  ATTENZIONE: {tot} SET da grammi di seme vs {richiesti} dichiarati: differenza accettata "
                      "esplicitamente; quantita' e grammi registrati NON vengono modificati.")
            print("  scelte: " + ", ".join(c["id"] for c in scelta))
            for c in scelta:
                if c["avvio"] > luce:
                    raise Stop(f"{c['id']}: avvio {c['avvio']} successivo alla luce {luce}.")
                scelte.append((c, nome))
        for pid in a.semina:
            if pid not in [c["id"] for c, _ in scelte]:
                raise Stop(f"{pid} non e' tra le semine AVVIATA/GERMINAZIONE delle varieta' richieste.")

        print("\n== Passaggi previsti")
        for c, nome in scelte:
            if c["stato"] == "AVVIATA":
                print(f"  {c['id']} {nome}: GERMINAZIONE {c['avvio'].astimezone(TZ):%Y-%m-%d %H:%M} (amministrativo, alla data di avvio)")
            print(f"  {c['id']} {nome}: LUCE {luce:%Y-%m-%d %H:%M}")
        if not a.esegui:
            print("\n(anteprima: nulla scritto)")
            return 0
        for c, nome in scelte:
            stato, version, prev = c["stato"], c["version"], c["avvio"]
            for target, t, nota in (("GERMINAZIONE", c["avvio"], "passaggio amministrativo alla data di avvio"),
                                    ("LUCE", luce, "stato fisico dichiarato da Matteo il 5/10/2026 (orario = registrazione)")):
                if stato == target or (target == "GERMINAZIONE" and stato != "AVVIATA"):
                    continue
                reason = f"Transizione {target} {c['id']} ({nome}): {nota}"
                cmd = [RUN, "semina", "transition", "--semina", c["id"], "--expected-semina-version", str(version),
                       "--target-state", target, "--effective-at", t.isoformat(), "--provenance", PROV,
                       "--actor", "matteo", "--reason", reason,
                       "--correlation-id", f"{TAG}-{c['id']}-{target}",
                       "--idempotency-key", f"{TAG}-{c['id']}-{target}", "--confirm"]
                print(f"\n[{c['id']}] -> {target} ({t.astimezone(TZ):%Y-%m-%d %H:%M})")
                done = subprocess.run(cmd, capture_output=True, text=True)
                print(done.stdout.rstrip())
                if done.returncode != 0:
                    print(done.stderr.rstrip(), file=sys.stderr)
                    raise Stop(f"{c['id']} -> {target} fallito (exit {done.returncode}); non rilancio altro.")
                stato, version = target, version + 1
    except Stop as exc:
        print(f"\nSTOP: {exc}")
        return 1
    finally:
        conn.close()
    print("\n== FINE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
