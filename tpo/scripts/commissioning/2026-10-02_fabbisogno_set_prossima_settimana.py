"""Fabbisogno SET per varieta' per la prossima settimana (lun-dom), per
consegnare a TUTTI i clienti con PROGRAMMA_FORNITURA ATTIVO.

Richiesta di Matteo 2/10/2026: "dammi le quantita di set per varieta che
necessito la prossima settimana per consegnare a tutti".

Calcola dinamicamente la "prossima settimana" (il lunedi successivo a
oggi, 7 giorni fino alla domenica) -- rilanciabile ogni settimana senza
modifiche. Legge SOLO i dati reali e correnti di
tpo.programmi_fornitura_versioni / righe_programma_fornitura /
righe_programma_giorni (stato ATTIVO, valida_al IS NULL, voided_at IS
NULL) -- nessun dato inventato, nessuna assunzione su quantita' o
ricorrenze.

Logica di occorrenza per riga:
  - GIORNI_SETTIMANA: la riga occorre in ogni giorno della settimana il
    cui ISO-weekday (lun=1..dom=7) e' in giorni_iso.
  - OGNI_X_GIORNI: la riga occorre nei giorni D tali che
    (D - data_inizio).days sia un multiplo non-negativo di
    intervallo_giorni.
  - Programmi SOSPESI/TERMINATI sono esclusi (nessuna consegna).

Output:
  1) Calendario consegne della settimana per cliente/varieta/giorno
     (utile per pianificare raccolta e consegna).
  2) Totale SET per varieta' sommato su tutta la settimana (la risposta
     diretta alla domanda di Matteo).

NOTA: questo e' il fabbisogno DI CONSEGNA (domanda lorda dai programmi di
fornitura), non ancora netto di eventuale produzione gia' in corso/
raccolti pianificati -- per quello serve il motore di produzione
governato (`tpo production-planning ...`), non ancora utilizzato qui.

Accetta un argomento opzionale: numero di settimane da saltare oltre la
prossima (0 = prossima settimana [default], 1 = quella dopo, ecc.).

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python3 scripts/commissioning/2026-10-02_fabbisogno_set_prossima_settimana.py
  .venv/bin/python3 scripts/commissioning/2026-10-02_fabbisogno_set_prossima_settimana.py 1
"""
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

GIORNI_NOME = {1: "lunedi", 2: "martedi", 3: "mercoledi", 4: "giovedi",
               5: "venerdi", 6: "sabato", 7: "domenica"}


def prossima_settimana(oggi: date) -> tuple[date, date]:
    giorni_al_prossimo_lunedi = (8 - oggi.isoweekday()) % 7
    if giorni_al_prossimo_lunedi == 0:
        giorni_al_prossimo_lunedi = 7
    inizio = oggi + timedelta(days=giorni_al_prossimo_lunedi)
    fine = inizio + timedelta(days=6)
    return inizio, fine


def occorre(riga, giorno: date) -> bool:
    tipo, intervallo, data_inizio, giorni_iso = riga
    if tipo == "GIORNI_SETTIMANA":
        return giorno.isoweekday() in giorni_iso
    if tipo == "OGNI_X_GIORNI":
        delta = (giorno - data_inizio).days
        return delta >= 0 and intervallo and delta % intervallo == 0
    return False


def db():
    p = load_postgresql_parameters()
    return psycopg.connect(
        host=p["host"], port=p["port"], dbname=p["dbname"],
        user=p["user"], password=p["password"], sslmode=p["sslmode"],
        connect_timeout=p["connect_timeout"],
    )


try:
    settimane_oltre = int(sys.argv[1]) if len(sys.argv) > 1 else 0
except ValueError:
    raise SystemExit("Argomento non valido: numero di settimane intero atteso.")
if settimane_oltre < 0:
    raise SystemExit("Argomento non valido: il numero di settimane deve essere >= 0.")

oggi = date.today()
inizio, fine = prossima_settimana(oggi)
inizio += timedelta(weeks=settimane_oltre)
fine += timedelta(weeks=settimane_oltre)
giorni_settimana = [inizio + timedelta(days=i) for i in range(7)]

etichetta = "prossima settimana" if settimane_oltre == 0 else f"settimana +{settimane_oltre + 1}"
print(f"Oggi: {oggi.isoformat()} ({GIORNI_NOME[oggi.isoweekday()]})")
print(f"{etichetta.capitalize()}: {inizio.isoformat()} ({GIORNI_NOME[1]}) "
      f"-> {fine.isoformat()} ({GIORNI_NOME[7]})\n")

conn = db()
try:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.denominazione, pf.public_id, rpf.id, v.denominazione,
                      rpf.quantita, rpf.tipo_ricorrenza, rpf.intervallo_giorni,
                      pv.data_inizio
               FROM tpo.programmi_fornitura_versioni pv
               JOIN tpo.programmi_fornitura pf ON pf.id = pv.programma_fornitura_id
               JOIN tpo.clienti c ON c.id = pv.cliente_id
               JOIN tpo.righe_programma_fornitura rpf ON rpf.programma_versione_id = pv.id
               JOIN tpo.varieta v ON v.id = rpf.varieta_id
               WHERE pv.valida_al IS NULL AND pv.voided_at IS NULL AND pv.stato = 'ATTIVO'
               ORDER BY c.denominazione, v.denominazione"""
        )
        righe_db = cur.fetchall()

        giorni_per_riga = {}
        for (cliente, pf_pid, riga_id, varieta, quantita, tipo, intervallo,
             data_inizio_pv) in righe_db:
            if tipo == "GIORNI_SETTIMANA":
                cur.execute(
                    "SELECT giorno_iso FROM tpo.righe_programma_giorni WHERE riga_programma_id=%s",
                    (riga_id,),
                )
                giorni_per_riga[riga_id] = {r[0] for r in cur.fetchall()}
            else:
                giorni_per_riga[riga_id] = set()
finally:
    conn.close()

calendario = defaultdict(list)  # giorno -> [(cliente, varieta, quantita)]
totale_varieta = defaultdict(lambda: Decimal("0"))

for (cliente, pf_pid, riga_id, varieta, quantita, tipo, intervallo,
     data_inizio_pv) in righe_db:
    giorni_iso = giorni_per_riga[riga_id]
    for giorno in giorni_settimana:
        if occorre((tipo, intervallo, data_inizio_pv, giorni_iso), giorno):
            calendario[giorno].append((cliente, varieta, quantita))
            totale_varieta[varieta] += quantita

print("=== Calendario consegne della settimana ===\n")
for giorno in giorni_settimana:
    voci = calendario.get(giorno, [])
    print(f"{GIORNI_NOME[giorno.isoweekday()].capitalize()} {giorno.isoformat()}:")
    if not voci:
        print("    (nessuna consegna)")
    else:
        for cliente, varieta, quantita in sorted(voci):
            print(f"    {cliente}: {varieta} {quantita} set")
    print()

print("=== Totale SET per varieta' -- settimana "
      f"{inizio.isoformat()} / {fine.isoformat()} ===\n")
if not totale_varieta:
    print("Nessuna consegna prevista questa settimana.")
else:
    for varieta, tot in sorted(totale_varieta.items(), key=lambda kv: -kv[1]):
        print(f"{varieta}: {tot} set")

print("\n=== FATTO ===")
