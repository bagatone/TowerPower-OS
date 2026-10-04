"""Registra a magazzino i materiali nuovi acquistati da Matteo (giovedi'
1/10/2026): 3000 substrati e 3000 vaschette, e scarica quanto e' stato
usato dalle semine fatte da giovedi' 1/10 a oggi 4/10/2026, SEMINA PER
SEMINA con il comando governato `tpo materiali consumo-semina` (cosi' ogni
SET e' tracciato sulla sua semina; lo stesso comando si usera' da ora per ogni
nuova semina).

Regola di consumo (dalla configurazione storica di Matteo,
src/init_resource_engine.py): 1 SET = 4 vaschette, 1 substrato per vaschetta
=> 4 substrati e 4 vaschette per ogni SET seminato.

SET seminati da giovedi' (dichiarati da Matteo; per il 1/10 dal suo
dettato "2 set cilantro, 2 set mizuna, 3 set rabano, 1 rucola, 2 basilico,
1 amaranto e 1 pak choy"; per il 2/10 "14 g" di Rabano = 1 SET; per il 4/10
7 SET Afila + 7 SET Cilantro). Lo script confronta questa lista con le
semine realmente presenti nel database dal 1/10 in poi e SI FERMA se non
coincidono (nessuna semina "dimenticata" e nessuna inventata).

STATO: ESEGUITO il 4/10/2026 (versione con consumo aggregato 108+108; giacenza
finale 2892 + 2892). Rilanciarlo registrerebbe i consumi due volte: se gli
articoli esistono gia', lo script si ferma subito senza scrivere. Per ogni
NUOVA semina usare `tpo materiali consumo-semina` (vedi sotto).

Senza --esegui NON scrive nulla (anteprima). Idempotente: ogni comando ha
idempotency-key fisse (un rilancio riproduce lo stesso esito, non duplica).

Uso, dalla cartella del progetto:
  .venv/bin/python scripts/commissioning/2026-10-04_registra_materiali.py            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-04_registra_materiali.py --esegui   # scrive
"""
import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402
import psycopg  # noqa: E402

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
ACTOR = "matteo"
TAG = "materiali-2026-10-04"
DA = date(2026, 10, 1)
ACQUISTO_AT = "2026-10-01T00:00:00+01:00"  # giovedi' 1/10 (ora non dichiarata: inizio giornata)
CONSUMO_AT = "2026-10-04T12:00:00+01:00"
PEZZI_PER_SET = 4  # 4 vaschette e 4 substrati per SET
ACQUISTATI = 3000

ARTICOLI = [("Substrato", "substrato"), ("Vaschette", "vaschette")]

SEMINE = {  # semina -> (varieta, SET, data)
    "SEM-000013": ("Cilantro", 2, "1/10"), "SEM-000014": ("Mizuna", 2, "1/10"),
    "SEM-000015": ("Rábano", 3, "1/10"), "SEM-000016": ("Amaranto", 1, "1/10"),
    "SEM-000017": ("Basilico", 2, "1/10"), "SEM-000018": ("Rucola", 1, "1/10"),
    "SEM-000019": ("Pak Choi", 1, "1/10"), "SEM-000020": ("Rábano", 1, "2/10"),
    "SEM-000021": ("Afila", 7, "4/10"), "SEM-000022": ("Cilantro", 7, "4/10"),
}


def kv(text: str, key: str):
    m = re.search(rf"^{re.escape(key)}[=:]\s*(\S+)", text, re.M)
    return m.group(1) if m else None


def stop(msg: str):
    raise SystemExit(f"STOP: {msg}")


def verifica_semine():
    p = load_postgresql_parameters()
    conn = psycopg.connect(
        host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
        password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"],
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT s.public_id, v.denominazione, s.data_avvio::date
                   FROM tpo.semine s JOIN tpo.varieta v ON v.id = s.varieta_id
                   WHERE s.data_avvio::date >= %s ORDER BY s.public_id""", (DA,))
            reali = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
            cur.execute("SELECT public_id FROM tpo.articoli ORDER BY public_id")
            esistenti = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    previste, trovate = set(SEMINE), set(reali)
    print("Semine dal 1/10 nel database:")
    for sid in sorted(reali):
        nome, giorno = reali[sid]
        dichiarate = SEMINE.get(sid)
        print(f"  {sid} {nome} {giorno}: " + (f"{dichiarate[1]} SET" if dichiarate else "NON in lista"))
    if previste != trovate:
        stop(f"le semine nel database non coincidono con la lista dichiarata. "
             f"Mancano nel database: {sorted(previste - trovate)}; non dichiarate: {sorted(trovate - previste)}. "
             "Dimmi quanti SET sono quelle in piu'/in meno.")
    for sid, (nome, _n, _g) in SEMINE.items():
        if reali[sid][0] != nome:
            stop(f"{sid} e' {reali[sid][0]} nel database, attesa {nome}.")
    return esistenti


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    args = ap.parse_args()
    esegui = args.esegui

    print(f"== MATERIALI -- {'ESECUZIONE' if esegui else 'ANTEPRIMA (nulla viene scritto)'}")
    esistenti = verifica_semine()
    if esistenti:
        print(f"\nGIA' ESEGUITO: esistono gia' gli articoli {', '.join(esistenti)} (carichi e consumo del 4/10 "
              "registrati). Non scrivo nulla: rilanciare duplicherebbe i consumi.\n"
              "Per una nuova semina: tpo materiali consumo-semina --semina SEM-... --set N ...")
        return 0
    tot_set = sum(n for _, n, _ in SEMINE.values())
    consumo = tot_set * PEZZI_PER_SET
    print(f"\nTotale SET seminati dal 1/10: {tot_set} -> consumo {consumo} substrati e {consumo} vaschette "
          f"({PEZZI_PER_SET} per SET). Giacenza attesa dopo: {ACQUISTATI - consumo} + {ACQUISTATI - consumo}.")

    def tpo(argv, label):
        shown = " ".join(a if re.fullmatch(r"[\w./:+=,@-]+", a) else repr(a) for a in argv)
        print(f"\n--- {label}\n$ tpo {shown}")
        if not esegui:
            print("   (anteprima: non eseguito)")
            return ""
        done = subprocess.run([RUN, *argv], capture_output=True, text=True)
        out = (done.stdout or "") + (done.stderr or "")
        print(out.rstrip())
        if done.returncode != 0:
            stop(f"comando fallito (exit {done.returncode}): {label}")
        return done.stdout

    for nome, chiave in ARTICOLI:
        out = tpo(["articolo", "commissiona", "--denominazione", nome, "--unita-misura", "UNIT",
                   "--actor", ACTOR, "--reason", f"Nuovo materiale di magazzino: {nome} (pezzi)",
                   "--correlation-id", f"{TAG}-articolo-{chiave}",
                   "--idempotency-key", f"{TAG}-articolo-{chiave}", "--confirm"], f"articolo {nome}")
        art = kv(out, "ARTICOLO_ID") or "ART-??????(da anteprima)"
        tpo(["movimento", "carica-articolo", "--articolo", art, "--quantita", str(ACQUISTATI),
             "--unita-misura", "UNIT", "--effective-at", ACQUISTO_AT,
             "--motivo", f"Acquisto di {ACQUISTATI} pezzi: {nome} (giovedi' 1/10/2026)",
             "--actor", ACTOR, "--reason", f"Acquisto di {ACQUISTATI} pezzi di {nome} dichiarato da Matteo il 4/10/2026",
             "--correlation-id", f"{TAG}-carico-{chiave}",
             "--idempotency-key", f"{TAG}-carico-{chiave}", "--confirm"], f"carico {nome} {ACQUISTATI}")

    for sid, (nome, n_set, giorno) in SEMINE.items():
        tpo(["materiali", "consumo-semina", "--semina", sid, "--set", str(n_set),
             "--pezzi-per-set", str(PEZZI_PER_SET),
             "--actor", ACTOR,
             "--reason", f"Consumo materiali della semina {sid} ({nome}, {n_set} SET, {giorno}), "
                         "dichiarato da Matteo il 4/10/2026",
             "--correlation-id", f"{TAG}-consumo-{sid}", "--confirm"],
            f"consumo {sid} {nome} {n_set} SET ({giorno}): -{n_set * PEZZI_PER_SET} vaschette e substrati")
    print("\n== FINE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
