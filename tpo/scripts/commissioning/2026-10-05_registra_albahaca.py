"""Registra la semina REALE di Albahaca (Basilico) di Matteo, registrata IN RITARDO il 5/10/2026:
2 SET seminati il 26/9/2026, passati in luce il 1/10/2026 (il basilico non ha idratazione).

  - grammi = grammi/SET della versione di protocollo APPROVATA corrente x SET dichiarati;
  - lotto di seme scelto con la stessa logica delle semine precedenti e MOSTRATO prima di scrivere;
  - il codice di tracciabilita' lo genera il sistema (ALB-2609-A se e' la prima del giorno);
  - orario di semina non rilevato: 09:00 convenzionale (--ora-semina), scritto nel motivo;
  - GERMINAZIONE: passaggio amministrativo allo stesso istante della semina (basilico senza
    idratazione), scritto nel motivo; LUCE alla data dichiarata (--luce-il);
  - CRESCITA e PRONTA_ALLA_RACCOLTA SOLO se indichi tu le date vere (--crescita-il, --pronta-il):
    senza, lo script si ferma in LUCE. Nessuna data viene inventata.

Senza --esegui NON scrive nulla (anteprima). Idempotente: si ferma/riprende da dove e' rimasta.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-05_registra_albahaca.py                 # anteprima
  .venv/bin/python scripts/commissioning/2026-10-05_registra_albahaca.py --esegui        # scrive fino a LUCE
  ... --esegui --crescita-il come-luce --pronta-il adesso                                # fino a PRONTA
    (--crescita-il / --pronta-il accettano anche una data ISO; "come-luce" = CRESCITA 1 minuto dopo
     la LUCE (stesso processo, regola di Matteo; il sistema vuole istanti strettamente crescenti); "adesso" = istante dell'esecuzione)
"""
import argparse
import importlib.util
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

_spec = importlib.util.spec_from_file_location(
    "commission_base", ROOT / "scripts" / "commissioning" / "2026-10-04_commission_semine_afila_cilantro.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

TZ = timezone(timedelta(hours=1))
RUN = base.RUN
NOME, SIGLA = "Basilico", "ALB"
TAG = "2026-10-05-albahaca"
PROV_TRANS = '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED"}'
CHAIN = ["AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA"]


def when(text):
    if text == "adesso":
        return datetime.now(TZ).replace(second=0, microsecond=0)
    d = datetime.fromisoformat(text)
    return d if d.tzinfo else d.replace(tzinfo=TZ)


def esegui(cmd, titolo):
    shown = " ".join(c if c and all(ch.isalnum() or ch in "-_./:+=,@" for ch in c) else repr(c) for c in cmd[1:])
    print(f"  $ tpo {shown}")
    done = subprocess.run(cmd, capture_output=True, text=True)
    print(done.stdout.rstrip())
    if done.returncode != 0:
        print(done.stderr.rstrip(), file=sys.stderr)
        base.stop(f"{titolo} fallito (exit {done.returncode}); non rilancio altro.")
    return done.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true")
    ap.add_argument("--set", type=int, default=2, dest="n_set")
    ap.add_argument("--varieta", default="Basilico", help="denominazione varieta' (default Basilico; per prove)")
    ap.add_argument("--data-semina", default="2026-09-26")
    ap.add_argument("--ora-semina", default="09:00")
    ap.add_argument("--luce-il", default="2026-10-01T07:00")
    ap.add_argument("--crescita-il")
    ap.add_argument("--pronta-il")
    a = ap.parse_args()

    global NOME
    NOME = a.varieta
    h, m = (int(x) for x in a.ora_semina.split(":"))
    giorno = datetime.fromisoformat(a.data_semina)
    started = datetime(giorno.year, giorno.month, giorno.day, h, m, tzinfo=TZ)
    luce = when(a.luce_il)
    steps = [("GERMINAZIONE", started,
              "passaggio amministrativo allo stesso istante della semina (basilico senza idratazione)"),
             ("LUCE", luce, "data dichiarata da Matteo")]
    if a.crescita_il:
        # REGOLA (Matteo, 5/10/2026): LUCE e CRESCITA sono lo stesso processo (indoor/outdoor):
        # "come-luce" registra CRESCITA 1 minuto dopo la LUCE.
        if a.crescita_il == "come-luce":
            # il sistema richiede istanti STRETTAMENTE crescenti: CRESCITA = LUCE + 1 minuto
            steps.append(("CRESCITA", luce + timedelta(minutes=1),
                          "stesso processo della luce (indoor/outdoor), regola dichiarata da Matteo; "
                          "registrata 1 minuto dopo la luce perche' gli istanti devono essere strettamente crescenti"))
        else:
            steps.append(("CRESCITA", when(a.crescita_il), "data dichiarata da Matteo"))
    if a.pronta_il:
        if not a.crescita_il:
            base.stop("--pronta-il richiede --crescita-il (gli stati non si saltano).")
        steps.append(("PRONTA_ALLA_RACCOLTA", when(a.pronta_il), "data dichiarata da Matteo"))
    prev = None
    for nome, t, _ in steps:
        if prev and t < prev:
            base.stop(f"{nome} {t:%Y-%m-%d %H:%M} precede lo stato precedente {prev:%Y-%m-%d %H:%M}.")
        prev = t
    if luce < started:
        base.stop("la luce precede la semina.")

    print(f"== ALBAHACA -- {'ESECUZIONE' if a.esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    conn = base.db()
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("""SELECT s.public_id, s.codice_tracciabilita, s.stato::text, s.version
                       FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
                       WHERE v.denominazione=%s AND s.data_avvio::date=%s""", (NOME, started.date()))
        esistenti = cur.fetchall()
        if len(esistenti) > 1:
            base.stop(f"piu' semine di {NOME} il {started.date()}: " + ", ".join(e[0] for e in esistenti))
        if esistenti:
            semina, codice, stato, version = esistenti[0]
            print(f"\nSemina gia' registrata: {semina} {codice} stato {stato}.")
        else:
            pv, per_set = base.resolve_protocol(cur, NOME)
            grams = per_set * a.n_set
            print(f"\nSemina {NOME}: {a.n_set} SET, avvio {started.isoformat()} (orario convenzionale)")
            print(f"  protocollo {pv}: {per_set} g/SET x {a.n_set} SET = {grams} g")
            lse, lver = base.resolve_seed_lot(cur, NOME, grams)
            reason = (f"Semina reale {NOME}/Albahaca del {started:%d/%m/%Y} ({a.n_set} SET, {grams.normalize():f} g), "
                      f"dichiarata da Matteo e registrata in ritardo il 5/10/2026; orario di semina non rilevato "
                      f"({a.ora_semina} convenzionale); cliente/ordine da assegnare in seguito.")
            cmd = [RUN, "semina", "commission", "--seed-lot", lse, "--expected-seed-lot-version", str(lver),
                   "--protocol-version", pv, "--actual-seed-grams", f"{grams.normalize():f}",
                   "--physical-started-at", started.isoformat(), "--origin", "RIPRISTINO_STOCK",
                   "--provenance", '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}',
                   "--actor", "matteo", "--reason", reason,
                   "--correlation-id", f"SEMINA-{TAG}", "--idempotency-key", f"semina-{SIGLA.lower()}-{started.date()}",
                   "--confirm"]
            if not a.esegui:
                print("  (anteprima) $ tpo semina commission ... (vedi sopra lotto e grammi)")
            else:
                esegui(cmd, "commissioning semina")
                cur.execute("""SELECT s.public_id, s.codice_tracciabilita, s.stato::text, s.version
                               FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
                               WHERE v.denominazione=%s AND s.data_avvio::date=%s""", (NOME, started.date()))
                semina, codice, stato, version = cur.fetchone()
            if not a.esegui:
                semina, codice, stato, version = "SEM-??????", f"{SIGLA}-{started:%d%m}-?", "AVVIATA", 0

        print(f"\nPassaggi di stato previsti per {semina} ({codice}):")
        for nome, t, nota in steps:
            fatto = CHAIN.index(stato) >= CHAIN.index(nome)
            print(f"  {nome:22} {t:%Y-%m-%d %H:%M}  {nota}" + ("  [gia' fatto]" if fatto else ""))
        if not a.crescita_il:
            print("  CRESCITA / PRONTA_ALLA_RACCOLTA: NON registrati (servono --crescita-il e --pronta-il con le date vere)")
        if not a.esegui:
            print("\n(anteprima: nulla scritto)")
            return 0
        cur.execute("SELECT max(effective_at) FROM tpo.semina_lifecycle_eventi e JOIN tpo.semine s ON s.id=e.semina_id "
                    "WHERE s.public_id=%s", (semina,))
        ultimo = cur.fetchone()[0]
        for nome, t, nota in steps:
            if CHAIN.index(stato) >= CHAIN.index(nome):
                continue
            if CHAIN.index(nome) != CHAIN.index(stato) + 1:
                base.stop(f"da {stato} a {nome} serve passare per uno stato intermedio non pianificato")
            if ultimo and t < ultimo:
                base.stop(f"{nome} {t:%Y-%m-%d %H:%M} precede l'ultimo evento {ultimo:%Y-%m-%d %H:%M}")
            reason = (f"Transizione {nome} {semina} del {t:%d/%m/%Y %H:%M}: {nota}; registrata in ritardo il "
                      "5/10/2026 su dichiarazione di Matteo")
            esegui([RUN, "semina", "transition", "--semina", semina, "--expected-semina-version", str(version),
                    "--target-state", nome, "--effective-at", t.isoformat(), "--provenance", PROV_TRANS,
                    "--actor", "matteo", "--reason", reason,
                    "--correlation-id", f"{TAG}-lifecycle-{semina}-{nome}",
                    "--idempotency-key", f"{TAG}-lifecycle-{semina}-{nome}", "--confirm"],
                   f"{semina} -> {nome}")
            stato, version, ultimo = nome, version + 1, t
    finally:
        conn.close()
    print("\n== FINE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
