"""Commissiona le due semine REALI di Matteo del 4/10/2026: Afila 7 SET e
Cilantro 7 SET ("appena piantato 7 set di afila e 7 di cilantro").

Stessa procedura governata usata il 1/10 e il 2/10 (`tpo semina commission`);
nessuna quantita' inventata:
  - i grammi per SET NON sono scritti qui: si leggono dalla versione di
    protocollo APPROVATA corrente (grammi_seme_per_set) e si moltiplicano per
    i SET dichiarati (7). Se il protocollo non e' unico, lo script si ferma.
  - il LOTTO_SEME si sceglie dalla stessa logica degli script precedenti
    (impiego raccomandato/utilizzabile, senza anomalia, non scaduto, scorta
    sufficiente) e viene MOSTRATO prima di scrivere.
  - il codice di tracciabilita' (AAA-GGMM-L) lo genera il sistema: qui si
    stampa solo quello restituito.

origin=RIPRISTINO_STOCK (nessun cliente/ordine assegnato, come le semine
precedenti; si puo' collegare dopo). Orario fisico di avvio: adesso (Matteo
ha detto "appena piantato"), modificabile con --ora HH:MM.

Senza --esegui NON scrive nulla (anteprima). Idempotente: se esiste gia'
una semina di quella varieta' con data_avvio = oggi, la salta.

Uso, dalla cartella del progetto:
  .venv/bin/python scripts/commissioning/2026-10-04_commission_semine_afila_cilantro.py            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-04_commission_semine_afila_cilantro.py --esegui   # scrive
"""
import argparse
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402
import psycopg  # noqa: E402

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
TZ = timezone(timedelta(hours=1))  # ora locale delle Canarie in ottobre (WEST)
TODAY = date(2026, 10, 4)
TAG = "2026-10-04"

SEMINE = [  # (varieta, sigla, SET dichiarati da Matteo)
    ("Afila", "AFI", 7),
    ("Cilantro", "CIL", 7),
]


def db():
    p = load_postgresql_parameters()
    return psycopg.connect(
        host=p["host"], port=p["port"], dbname=p["dbname"],
        user=p["user"], password=p["password"], sslmode=p["sslmode"],
        connect_timeout=p["connect_timeout"],
    )


def stop(msg: str):
    raise SystemExit(f"STOP: {msg}")


def resolve_protocol(cur, nome):
    cur.execute(
        """SELECT pv.public_id, pv.grammi_seme_per_set
           FROM tpo.protocollo_versioni pv
           JOIN tpo.protocolli p ON p.id = pv.protocollo_id
           JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id
           JOIN tpo.cultivar c ON c.id = cu.cultivar_id
           JOIN tpo.varieta v ON v.id = c.varieta_id
           JOIN tpo.usi_produttivi up ON up.id = cu.uso_produttivo_id AND up.codice = 'MICROGREEN'
           WHERE v.denominazione = %s AND pv.stato_approvazione = 'APPROVATA'
             AND pv.valida_al IS NULL""",
        (nome,),
    )
    rows = cur.fetchall()
    if len(rows) != 1:
        stop(f"{nome}: trovate {len(rows)} versioni di protocollo APPROVATE correnti, attesa 1.")
    return rows[0][0], Decimal(rows[0][1])


def resolve_seed_lot(cur, nome, needed_grams):
    cur.execute(
        """SELECT s.id, s.fornitore, si.raccomandazione, si.rating
           FROM tpo.semente_impieghi si
           JOIN tpo.sementi s ON s.id = si.semente_id
           JOIN tpo.cultivar_usi cu ON cu.id = si.cultivar_uso_id
           JOIN tpo.cultivar c ON c.id = cu.cultivar_id
           JOIN tpo.varieta v ON v.id = c.varieta_id
           WHERE v.denominazione = %s AND si.raccomandazione IN ('RACCOMANDATA', 'UTILIZZABILE')
           ORDER BY si.raccomandazione, si.rating DESC NULLS LAST""",
        (nome,),
    )
    impieghi = cur.fetchall()
    if not impieghi:
        stop(f"{nome}: nessun impiego di seme eleggibile collegato.")
    motivi = []
    for semente_id, fornitore, racc, _rating in impieghi:
        cur.execute(
            """SELECT public_id, version, quantita_residua, anomalia IS NOT NULL
               FROM tpo.lotti_seme
               WHERE semente_id = %s
                 AND (data_scadenza IS NULL OR data_scadenza >= %s)
               ORDER BY data_ricezione DESC""",
            (semente_id, TODAY),
        )
        for pid, version, residuo, ha_anomalia in cur.fetchall():
            if ha_anomalia:
                motivi.append(f"{pid} ({fornitore}): ha un'anomalia registrata")
            elif residuo < needed_grams:
                motivi.append(f"{pid} ({fornitore}): residuo {residuo} g < {needed_grams} g necessari")
            else:
                print(f"  lotto scelto {pid} ({fornitore}, {racc}), residuo {residuo} g, servono {needed_grams} g")
                return pid, version
    stop(f"{nome}: nessun lotto utilizzabile. " + "; ".join(motivi))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    parser.add_argument("--ora", default=None, help="ora fisica di semina HH:MM (default: adesso)")
    args = parser.parse_args()

    if args.ora:
        h, m = (int(x) for x in args.ora.split(":"))
        started = datetime(TODAY.year, TODAY.month, TODAY.day, h, m, tzinfo=TZ)
    else:
        started = datetime.now(TZ).replace(second=0, microsecond=0)
        if started.date() != TODAY:
            stop(f"oggi non e' il {TODAY}: indica l'ora con --ora HH:MM")

    print(f"== SEMINE {TODAY} -- {'ESECUZIONE' if args.esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    conn = db()
    try:
        with conn.cursor() as cur:
            for nome, sigla, n_set in SEMINE:
                print(f"\n=== {nome} ({sigla}): {n_set} SET ===")
                cur.execute(
                    "SELECT s.public_id, s.codice_tracciabilita FROM tpo.semine s "
                    "JOIN tpo.varieta v ON v.id = s.varieta_id "
                    "WHERE v.codice_tracciabilita = %s AND s.data_avvio::date = %s",
                    (sigla, TODAY),
                )
                esistenti = cur.fetchall()
                if esistenti:
                    print(f"  gia' commissionata oggi: {esistenti[0][0]} ({esistenti[0][1]}). Salto.")
                    continue
                pv, per_set = resolve_protocol(cur, nome)
                grams = per_set * n_set
                print(f"  protocollo {pv}: {per_set} g/SET x {n_set} SET = {grams} g")
                lse, version = resolve_seed_lot(cur, nome, grams)
                cmd = [
                    RUN, "semina", "commission",
                    "--seed-lot", lse, "--expected-seed-lot-version", str(version),
                    "--protocol-version", pv, "--actual-seed-grams", f"{grams.normalize():f}",
                    "--physical-started-at", started.isoformat(),
                    "--origin", "RIPRISTINO_STOCK",
                    "--provenance", '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}',
                    "--actor", "matteo",
                    "--reason", (f"Semina reale {nome} del 4/10/2026 ({n_set} SET, {grams.normalize():f} g), "
                                 "dichiarata da Matteo; cliente/ordine da assegnare in seguito."),
                    "--correlation-id", f"SEMINA-{TAG}-{sigla}",
                    "--idempotency-key", f"semina-{sigla.lower()}-{TAG}",
                    "--confirm",
                ]
                shown = " ".join(c if c and all(ch.isalnum() or ch in "-_./:+=,@" for ch in c) else repr(c) for c in cmd[1:])
                print(f"  $ tpo {shown}")
                if not args.esegui:
                    print("  (anteprima: non eseguito)")
                    continue
                done = subprocess.run(cmd, capture_output=True, text=True)
                print(done.stdout.rstrip())
                if done.returncode != 0:
                    print(done.stderr.rstrip(), file=sys.stderr)
                    stop(f"commissioning {nome} fallito (exit {done.returncode}); non rilancio altro.")
    finally:
        conn.close()
    print("\n== FINE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
