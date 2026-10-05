"""Chiude una semina con l'esito finale dichiarato da Matteo (5/10/2026):
  SEM-000003 (Amaranto 7/9, AVVIATA, 1 SET): 0.5 SET venduto, 0.5 SET scartato (collassato, non vendibile)
  -> esito "raccolta parziale con scarto".

Come SEM-000006 il 3/10: nessuna RACCOLTA ne' movimento di magazzino viene creato (il sistema accetta
raccolte solo da semine PRONTA_ALLA_RACCOLTA e non si inventano date di stadio): le quantita' restano
scritte nella motivazione. Non tocca stock, ordini, consegne ne' i grammi registrati.

Senza --esegui NON scrive nulla (anteprima). Idempotente (se gia' CHIUSA, salta).

Uso:
  .venv/bin/python scripts/commissioning/2026-10-05_chiudi_semina.py            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-05_chiudi_semina.py --esegui
"""
import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402
import psycopg  # noqa: E402

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
TZ = timezone(timedelta(hours=1))
ESITI = ["raccolta completa", "raccolta parziale con scarto", "scarto totale", "interruzione"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true")
    ap.add_argument("--semina", default="SEM-000003")
    ap.add_argument("--esito", default="raccolta parziale con scarto", choices=ESITI)
    ap.add_argument("--venduti", default="0.5", help="SET venduti (dichiarati)")
    ap.add_argument("--scartati", default="0.5", help="SET scartati (dichiarati)")
    ap.add_argument("--chiusa-il", default="adesso", help='ISO 8601 oppure "adesso"')
    a = ap.parse_args()
    t = (datetime.now(TZ).replace(second=0, microsecond=0) if a.chiusa_il == "adesso"
         else datetime.fromisoformat(a.chiusa_il))
    if t.tzinfo is None:
        t = t.replace(tzinfo=TZ)
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"],
                           connect_timeout=p["connect_timeout"], autocommit=True)
    cur = conn.cursor()
    print(f"== CHIUSURA {a.semina} -- {'ESECUZIONE' if a.esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    try:
        cur.execute("""SELECT s.stato::text, s.version, s.codice_tracciabilita, v.denominazione, s.data_avvio,
                              s.quantita_seme,
                              (SELECT count(*) FROM tpo.raccolte r WHERE r.semina_id=s.id),
                              (SELECT max(e.effective_at) FROM tpo.semina_lifecycle_eventi e WHERE e.semina_id=s.id)
                       FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id WHERE s.public_id=%s""", (a.semina,))
        row = cur.fetchone()
        if not row:
            print(f"STOP: {a.semina} inesistente.")
            return 1
        stato, version, codice, varieta, avvio, grammi, n_racc, ultimo = row
        print(f"{a.semina} {codice} {varieta}: stato {stato}, versione {version}, avvio {avvio:%Y-%m-%d}, "
              f"{grammi} g, raccolte registrate: {n_racc}")
        if stato == "CHIUSA":
            print("Gia' CHIUSA: salto.")
            return 0
        if n_racc:
            print("STOP: esistono raccolte registrate per questa semina: l'esito va scelto con piu' attenzione.")
            return 1
        if ultimo and t < ultimo:
            print(f"STOP: chiusura {t} precede l'ultimo evento {ultimo}.")
            return 1
        reason = (f"Chiusura {a.semina} ({varieta} {avvio:%d/%m/%Y}) dichiarata da Matteo il 5/10/2026: "
                  f"{a.venduti} SET venduto (vendita non registrata) e {a.scartati} SET scartato "
                  "(collassato, non vendibile). Nessuna RACCOLTA ne' movimento di magazzino registrato per questa semina.")
        cmd = [RUN, "semina", "transition", "--semina", a.semina, "--expected-semina-version", str(version),
               "--target-state", "CHIUSA", "--effective-at", t.isoformat(), "--final-outcome", a.esito,
               "--provenance", '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED","final_outcome":"OWNER_AUTHORIZED"}',
               "--actor", "matteo", "--reason", reason,
               "--correlation-id", f"chiusura-2026-10-05-{a.semina}",
               "--idempotency-key", f"chiusura-2026-10-05-{a.semina}", "--confirm"]
        print(f"\nChiuderei con esito \"{a.esito}\" alle {t:%Y-%m-%d %H:%M}\nMotivo: {reason}")
        if not a.esegui:
            print("\n(anteprima: nulla scritto)")
            return 0
        done = subprocess.run(cmd, capture_output=True, text=True)
        print(done.stdout.rstrip())
        if done.returncode != 0:
            print(done.stderr.rstrip(), file=sys.stderr)
            return 1
    finally:
        conn.close()
    print("\n== FINE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
