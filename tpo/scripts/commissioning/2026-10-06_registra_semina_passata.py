"""Registra una semina REALE avvenuta nei giorni scorsi e MAI registrata (dichiarata da Matteo il 6/10/2026):
Hinojo, 1 SET, seminato "7 giorni fa" = 29/9/2026, ora in GERMINAZIONE.

Stessa procedura governata delle semine precedenti, nessun dato inventato:
  1. `tpo semina commission` (AVVIATA, origin RIPRISTINO_STOCK, nessun cliente/ordine):
     grammi = grammi/SET della versione di protocollo APPROVATA corrente x SET dichiarati; lotto di seme scelto
     con la logica di sempre e MOSTRATO prima di scrivere; codice e SEM-... li genera il sistema.
     La data e' STIMATA da Matteo ("7 giorni fa") e l'ora e' convenzionale (--ora-semina, default 09:00):
     entrambe sono scritte nel motivo, non presentate come misurate.
  2. GERMINAZIONE: passaggio amministrativo allo stesso istante della semina (come per le altre semine).
     LUCE e oltre NON vengono registrate (il seme e' ancora in germinazione).
  3. Resa attesa e finestra di raccolta (comando governato `semina_predictive_authority`, SET dichiarati):
     la finestra deriva dalla data di semina + giorni del protocollo, quindi e' stimata quanto la data.
  NON registra consumo materiali: la semina e' anteriore al 1/10, quando Matteo ha iniziato a usare i
  materiali comprati (3000 vaschette e 3000 substrati); scaricarli ora falserebbe quella scorta.

Senza --esegui NON scrive nulla (anteprima). Rilanciabile: se la semina del giorno esiste gia' riprende da dove
si era fermata (stato e predittivo gia' fatti vengono saltati).

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-06_registra_semina_passata.py            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-06_registra_semina_passata.py --esegui   # scrive
  opzioni: --varieta Hinojo --set 1 --data-semina 2026-09-29 --ora-semina 09:00
"""
import argparse
import importlib.util
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

from src.tpo_core.application.production_planning.in_progress_authority import (  # noqa: E402
    DEFAULT_WINDOW_DAYS, derive_in_progress_authority,
)
from src.tpo_core.infrastructure.postgresql import semina_predictive_authority as authority  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "commission_base", ROOT / "scripts" / "commissioning" / "2026-10-04_commission_semine_afila_cilantro.py")
base = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = base
_spec.loader.exec_module(base)

TZ = timezone(timedelta(hours=1))
RUN = base.RUN
TAG = "2026-10-06-semina-passata"
PROV_COMMISSION = ('{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED",'
                   '"selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}')
PROV_TRANS = '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED"}'
PROV_PREDICTIVE = ('{"declared_sets":"OWNER_AUTHORIZED","harvest_window_days":"OWNER_AUTHORIZED",'
                   '"derivation":"PROTOCOL_VERSION"}')


def shown(cmd):
    return " ".join(c if c and all(ch.isalnum() or ch in "-_./:+=,@" for ch in c) else repr(c) for c in cmd[1:])


def esegui(cmd, titolo):
    print(f"  $ tpo {shown(cmd)}")
    done = subprocess.run(cmd, capture_output=True, text=True)
    print(done.stdout.rstrip())
    if done.returncode != 0:
        print(done.stderr.rstrip(), file=sys.stderr)
        base.stop(f"{titolo} fallito (exit {done.returncode}); non rilancio altro.")


def find(cur, nome, giorno):
    cur.execute("""SELECT s.public_id, s.codice_tracciabilita, s.stato::text, s.version,
                          s.expected_useful_quantity IS NOT NULL
                   FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
                   WHERE v.denominazione=%s AND s.data_avvio::date=%s ORDER BY s.id""", (nome, giorno))
    return cur.fetchall()


def protocol_row(cur, pv):
    cur.execute("""SELECT resa_attesa, resa_unita_misura::text, germinazione_giorni, crescita_luce_giorni,
                          buffer_temporale_minuti FROM tpo.protocollo_versioni WHERE public_id=%s""", (pv,))
    return cur.fetchone()


def expected_window(cur, pv, n_set, started, window_days):
    row = protocol_row(cur, pv)
    return derive_in_progress_authority(
        declared_sets=n_set, expected_yield=Decimal(row[0]), yield_uom=row[1], started_at=started,
        germination_days=int(row[2]), light_days=int(row[3]), buffer_minutes=int(row[4] or 0), window_days=window_days)


def run(conn, predictive_conn_factory, esegui_scrittura: bool, nome: str, n_set: int, giorno: date, ora: str,
        window_days: int = DEFAULT_WINDOW_DAYS) -> tuple[str, str]:
    base.TODAY = giorno  # scadenza lotti valutata alla data di semina
    h, m = (int(x) for x in ora.split(":"))
    started = datetime(giorno.year, giorno.month, giorno.day, h, m, tzinfo=TZ)
    cur = conn.cursor()
    slug = nome.lower().replace(" ", "-")
    print(f"\n=== {nome}: {n_set} SET, avvio {started:%d/%m/%Y %H:%M} (data stimata da Matteo, ora convenzionale) ===")
    esistenti = find(cur, nome, giorno)
    if len(esistenti) > 1:
        base.stop(f"piu' semine di {nome} il {giorno}: " + ", ".join(e[0] for e in esistenti))
    pv, per_set = base.resolve_protocol(cur, nome)
    grams = per_set * n_set
    if esistenti:
        semina, codice, stato, version, filled = esistenti[0]
        print(f"  semina gia' registrata: {semina} ({codice}) stato {stato}. Salto il commissioning.")
    else:
        print(f"  protocollo {pv}: {per_set} g/SET x {n_set} SET = {grams} g")
        lse, lver = base.resolve_seed_lot(cur, nome, grams)
        reason = (f"Semina reale {nome} {n_set} SET ({grams.normalize():f} g), mai registrata, dichiarata da Matteo il "
                  f"6/10/2026: seminata circa 7 giorni prima, data stimata {giorno:%d/%m/%Y} e ora di semina non "
                  f"rilevata ({ora} convenzionale); ora in germinazione; cliente/ordine da assegnare in seguito.")
        cmd = [RUN, "semina", "commission", "--seed-lot", lse, "--expected-seed-lot-version", str(lver),
               "--protocol-version", pv, "--actual-seed-grams", f"{grams.normalize():f}",
               "--physical-started-at", started.isoformat(), "--origin", "RIPRISTINO_STOCK",
               "--provenance", PROV_COMMISSION, "--actor", "matteo", "--reason", reason,
               "--correlation-id", f"SEMINA-{TAG}-{slug}", "--idempotency-key", f"semina-{slug}-{giorno}",
               "--confirm"]
        if not esegui_scrittura:
            print(f"  (anteprima) $ tpo {shown(cmd)}")
            semina, codice, stato, version, filled = "SEM-??????", f"{nome[:3].upper()}-{giorno:%d%m}-?", "AVVIATA", 0, False
        else:
            esegui(cmd, f"commissioning {nome}")
            trovate = find(cur, nome, giorno)
            if len(trovate) != 1:
                base.stop(f"dopo il commissioning di {nome} attesa 1 semina del {giorno}, trovate {len(trovate)}.")
            semina, codice, stato, version, filled = trovate[0]

    window = expected_window(cur, pv, n_set, started, window_days)
    print(f"\n  Passaggi per {semina} ({codice}):")
    print(f"    GERMINAZIONE {started:%Y-%m-%d %H:%M}  (amministrativo, allo stesso istante della semina)"
          + ("  [gia' fatto]" if stato != "AVVIATA" else ""))
    print("    LUCE e oltre: NON registrati (ancora in germinazione)")
    if window:
        print(f"    resa attesa {window.quantity.normalize():f} {window.uom}, finestra di raccolta "
              f"{window.window_start:%Y-%m-%d} -> {window.window_end:%Y-%m-%d} (derivata dalla data stimata)"
              + ("  [gia' compilata]" if filled else ""))
    print("    consumo materiali: NON registrato (semina anteriore al 1/10, scorta nuova non toccata)")
    if not esegui_scrittura:
        return semina, codice

    if stato == "AVVIATA":
        reason = (f"Transizione GERMINAZIONE {semina} del {started:%d/%m/%Y %H:%M}: passaggio amministrativo allo "
                  "stesso istante della semina (data stimata), registrata in ritardo il 6/10/2026 su dichiarazione di Matteo")
        esegui([RUN, "semina", "transition", "--semina", semina, "--expected-semina-version", str(version),
                "--target-state", "GERMINAZIONE", "--effective-at", started.isoformat(), "--provenance", PROV_TRANS,
                "--actor", "matteo", "--reason", reason, "--correlation-id", f"{TAG}-{semina}-GERMINAZIONE",
                "--idempotency-key", f"{TAG}-{semina}-GERMINAZIONE", "--confirm"], f"{semina} -> GERMINAZIONE")
    if not filled:
        pconn = predictive_conn_factory()
        try:
            pcur = pconn.cursor()
            done, _ = authority.commission_predictive(
                pcur, declared_sets={semina: n_set}, actor="matteo",
                reason=(f"Resa attesa e finestra di raccolta ({window_days} giorni) di {semina} ({nome} {n_set} SET), "
                        "derivate dal protocollo e dalla data di semina stimata da Matteo il 6/10/2026."),
                correlation_id=f"{TAG}-{semina}-predittivo", provenance=PROV_PREDICTIVE, window_days=window_days)
            pconn.commit()
        except Exception:
            pconn.rollback()
            raise
        finally:
            pconn.close()
        print(f"  Resa attesa e finestra compilate per: {', '.join(done)}")
    return semina, codice


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: anteprima)")
    ap.add_argument("--varieta", default="Hinojo")
    ap.add_argument("--set", type=int, default=1, dest="n_set")
    ap.add_argument("--data-semina", default="2026-09-29")
    ap.add_argument("--ora-semina", default="09:00")
    ap.add_argument("--giorni-finestra", type=int, default=DEFAULT_WINDOW_DAYS)
    a = ap.parse_args()
    if a.n_set < 1:
        base.stop("--set deve essere un intero >= 1.")
    giorno = date.fromisoformat(a.data_semina)
    print(f"== SEMINA PASSATA {a.varieta} -- {'ESECUZIONE' if a.esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    conn = base.db()
    conn.autocommit = True
    try:
        semina, codice = run(conn, base.db, a.esegui, a.varieta, a.n_set, giorno, a.ora_semina, a.giorni_finestra)
    finally:
        conn.close()
    print(f"\n== RIEPILOGO\n  {a.varieta} {a.n_set} SET  {semina}  {codice}")
    print("\n== FINE" + ("" if a.esegui else " (anteprima: nulla scritto; per scrivere aggiungi --esegui)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
