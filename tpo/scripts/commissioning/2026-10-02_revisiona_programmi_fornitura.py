"""Revisiona 4 PROGRAMMI_FORNITURA attivi (Tagoro, Azul y Sal, Alchimia Sushi,
Selvaje) secondo le modifiche dettate da Matteo il 2/10/2026, e sospende
Margot a tempo indeterminato.

Dati PRIMA (da 2026-10-02_dettaglio_programmi_fornitura.py, rilanciato e
confermato da Matteo il 2/10/2026):
  Tagoro     PF-000002 v2 ATTIVO  -- Cilantro 1 SET GIORNI_SETTIMANA gg=[2] (martedi)
  Azul y Sal PF-000005 v2 ATTIVO  -- Cilantro 5 SET GIORNI_SETTIMANA gg=[5] (venerdi)
  Alchimia   PF-000003 v2 ATTIVO  -- Afila/Mizuna/Rabano/Hinojo 1 SET ciascuna GIORNI_SETTIMANA gg=[4] (giovedi)
  Selvaje    PF-000004 v3 SOSPESO -- Afila 2 SET + Cilantro 1 SET GIORNI_SETTIMANA gg=[4] (giovedi)
  Margot     PF-000006 v2 ATTIVO

Richieste di Matteo (chat 2/10/2026):
  - Tagoro: "1 cilantro ogni due settimane" -> stessa quantita' (1 SET),
    passa da settimanale a OGNI_X_GIORNI intervallo=14. data_inizio della
    versione resta 2026-08-25 (martedi) invariata: 2026-08-25 + 14*3gg =
    6/10/2026 (martedi), stesso giorno di consegna storico, nessuna nuova
    ancora necessaria.
  - Azul y Sal: "3 a settimana" -> quantita' 5->3 SET, resta settimanale
    venerdi (nessun cambio di tipo/giorno).
  - Alchimia: "dimezza a meta' di ogni varieta' con consegna il venerdi"
    -> tutte e 4 le righe 1->0.5 SET, giorno 4(giovedi)->5(venerdi).
  - Selvaje: "adesso facciamo 3 set ogni due settimane, 2 afila ed 1
    cilantro" + "il 9 siamo in consegna, quindi dobbiamo gia esser in
    produzione" + "se dobbiamo consegnare giovedi prossimo la produzione
    deve gia essere avviata da mo" -> riattiva (SOSPESO->ATTIVO) E CAMBIA
    tipo riga da GIORNI_SETTIMANA a OGNI_X_GIORNI intervallo=14, stesse
    quantita' gia' presenti nella v3 sospesa (2 Afila + 1 Cilantro).
    data_inizio versione resta 2026-08-27 (giovedi) invariata:
    2026-08-27 + 14*3gg = 8/10/2026 (giovedi prossimo), esattamente il
    giorno richiesto -- nessuna nuova ancora necessaria.
  - Margot: "sospeso" / "a tempo indeterminato" -> sospensione A TEMPO
    INDETERMINATO (nessuna data_ripresa_prevista) via comando governato
    reale 'tpo programma-fornitura sospendi' (nessuno script manuale
    necessario per questo).

Nessun comando CLI esiste per "modifica righe di un PROGRAMMA_FORNITURA
gia' attivo" (gap noto: solo sospendi/riattiva/onboarding/correct-never-
effective esistono) -- le 4 revisioni sotto replicano esattamente lo
schema reale _close_and_insert_version() di
src/tpo_core/infrastructure/postgresql/programma_fornitura_sospensione.py
(chiudi versione corrente con valida_al=now, inserisci nuova versione con
stesso programma_fornitura_id/cliente_id/data_inizio/data_fine/
orario_generazione/finestra_operativa_giorni, nuove righe_programma_
fornitura + righe_programma_giorni), con audit_eventi manuale -- stesso
genere di correzione gia' fatto per le anomalie LSE.

Idempotente: se la versione corrente di un programma e' gia' > versione
attesa, salta (assume gia' applicato). Margot: se gia' SOSPESO, salta.

Uso: dalla cartella del progetto, con il venv attivato:
  .venv/bin/python3 scripts/commissioning/2026-10-02_revisiona_programmi_fornitura.py
"""
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg
from psycopg.types.json import Jsonb

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
ACTOR = "matteo"

REVISIONS = [
    {
        "pf": "PF-000002", "nome": "Tagoro", "expected_numero_versione": 2,
        "target_stato": "ATTIVO",
        "lines": [
            {"varieta": "VAR-000003", "quantita": "1", "tipo_ricorrenza": "OGNI_X_GIORNI",
             "intervallo_giorni": 14, "giorni_iso": None},
        ],
        "reason": (
            "Richiesta Matteo 2/10/2026: Cilantro 1 SET ogni due settimane "
            "(era settimanale martedi). data_inizio versione invariata "
            "(2026-08-25, martedi): nuova ricorrenza OGNI_X_GIORNI=14 cade "
            "comunque di martedi (6/10/2026), nessun cambio di giorno di consegna."
        ),
    },
    {
        "pf": "PF-000005", "nome": "Azul y Sal", "expected_numero_versione": 2,
        "target_stato": "ATTIVO",
        "lines": [
            {"varieta": "VAR-000003", "quantita": "3", "tipo_ricorrenza": "GIORNI_SETTIMANA",
             "intervallo_giorni": None, "giorni_iso": [5]},
        ],
        "reason": "Richiesta Matteo 2/10/2026: Cilantro 5->3 SET a settimana, resta venerdi.",
    },
    {
        "pf": "PF-000003", "nome": "Alchimia Sushi", "expected_numero_versione": 2,
        "target_stato": "ATTIVO",
        "lines": [
            {"varieta": "VAR-000001", "quantita": "0.5", "tipo_ricorrenza": "GIORNI_SETTIMANA",
             "intervallo_giorni": None, "giorni_iso": [5]},
            {"varieta": "VAR-000004", "quantita": "0.5", "tipo_ricorrenza": "GIORNI_SETTIMANA",
             "intervallo_giorni": None, "giorni_iso": [5]},
            {"varieta": "VAR-000002", "quantita": "0.5", "tipo_ricorrenza": "GIORNI_SETTIMANA",
             "intervallo_giorni": None, "giorni_iso": [5]},
            {"varieta": "VAR-000005", "quantita": "0.5", "tipo_ricorrenza": "GIORNI_SETTIMANA",
             "intervallo_giorni": None, "giorni_iso": [5]},
        ],
        "reason": (
            "Richiesta Matteo 2/10/2026: dimezza ogni varieta' a 0.5 SET "
            "(Afila/Mizuna/Rabano/Hinojo, erano 1 SET ciascuna) e sposta "
            "la consegna da giovedi a venerdi."
        ),
    },
    {
        "pf": "PF-000004", "nome": "Selvaje", "expected_numero_versione": 3,
        "target_stato": "ATTIVO",
        "lines": [
            {"varieta": "VAR-000001", "quantita": "2", "tipo_ricorrenza": "OGNI_X_GIORNI",
             "intervallo_giorni": 14, "giorni_iso": None},
            {"varieta": "VAR-000003", "quantita": "1", "tipo_ricorrenza": "OGNI_X_GIORNI",
             "intervallo_giorni": 14, "giorni_iso": None},
        ],
        "reason": (
            "Richiesta Matteo 2/10/2026: riattiva Selvaje (era SOSPESO) con "
            "nuovo ritmo ogni 14 giorni, stesse quantita' di prima (2 Afila "
            "+ 1 Cilantro). Consegna richiesta giovedi prossimo (8/10/2026): "
            "'se dobbiamo consegnare giovedi prossimo la produzione deve "
            "gia essere avviata da mo'. data_inizio versione invariata "
            "(2026-08-27, giovedi): 2026-08-27 + 14*3gg = 8/10/2026, "
            "esattamente il giovedi richiesto."
        ),
    },
]


def db():
    p = load_postgresql_parameters()
    return psycopg.connect(
        host=p["host"], port=p["port"], dbname=p["dbname"],
        user=p["user"], password=p["password"], sslmode=p["sslmode"],
        connect_timeout=p["connect_timeout"],
    )


def varieta_id(cur, public_id):
    cur.execute("SELECT id FROM tpo.varieta WHERE public_id=%s", (public_id,))
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"VARIETA {public_id} non trovata.")
    return row[0]


def revisiona(conn, spec):
    nome, pf_pid = spec["nome"], spec["pf"]
    print(f"=== {nome} ({pf_pid}) ===")
    with conn.cursor() as cur:
        cur.execute(
            """SELECT p.id,p.cliente_id,p.public_id,pv.id,pv.numero_versione,pv.stato,
                      pv.data_inizio,pv.data_fine,pv.orario_generazione,
                      pv.finestra_operativa_giorni
               FROM tpo.programmi_fornitura p
               JOIN tpo.programmi_fornitura_versioni pv
                 ON pv.programma_fornitura_id=p.id
               WHERE p.public_id=%s AND pv.valida_al IS NULL AND pv.voided_at IS NULL
               FOR UPDATE OF p,pv""",
            (pf_pid,),
        )
        row = cur.fetchone()
        if row is None:
            raise SystemExit(f"{pf_pid} non trovato o privo di versione corrente.")
        (program_pk, cliente_id, _pid, old_version_pk, numero_versione, stato_corrente,
         data_inizio, data_fine, orario_generazione, finestra) = row

        if numero_versione > spec["expected_numero_versione"]:
            print(f"{nome}: versione corrente e' gia' v{numero_versione} "
                  f"(attesa v{spec['expected_numero_versione']}). Assumo gia' applicato, salto.")
            conn.rollback()
            return
        if numero_versione != spec["expected_numero_versione"]:
            raise SystemExit(
                f"{nome}: versione corrente v{numero_versione}, attesa "
                f"v{spec['expected_numero_versione']}. Fermo per revisione manuale."
            )

        now = datetime.now(timezone.utc)
        cur.execute(
            """UPDATE tpo.programmi_fornitura_versioni SET valida_al=%s
               WHERE id=%s AND valida_al IS NULL""",
            (now, old_version_pk),
        )
        if cur.rowcount != 1:
            raise SystemExit(f"{nome}: conflitto concorrente sulla versione corrente.")

        new_version = numero_versione + 1
        cur.execute(
            """INSERT INTO tpo.programmi_fornitura_versioni
               (programma_fornitura_id,cliente_id,numero_versione,stato,data_inizio,
                data_fine,orario_generazione,finestra_operativa_giorni,valida_dal,
                valida_al,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s) RETURNING id""",
            (program_pk, cliente_id, new_version, spec["target_stato"], data_inizio,
             data_fine, orario_generazione, finestra, now, ACTOR),
        )
        new_version_pk = cur.fetchone()[0]

        after_lines = []
        for posizione, line in enumerate(spec["lines"], start=1):
            vid = varieta_id(cur, line["varieta"])
            cur.execute(
                """INSERT INTO tpo.righe_programma_fornitura
                   (programma_versione_id,posizione,varieta_id,quantita,unita_misura,
                    tipo_ricorrenza,intervallo_giorni)
                   VALUES (%s,%s,%s,%s,'SET',%s,%s) RETURNING id""",
                (new_version_pk, posizione, vid, Decimal(line["quantita"]),
                 line["tipo_ricorrenza"], line["intervallo_giorni"]),
            )
            new_riga_id = cur.fetchone()[0]
            if line["giorni_iso"]:
                for giorno in line["giorni_iso"]:
                    cur.execute(
                        "INSERT INTO tpo.righe_programma_giorni(riga_programma_id,giorno_iso) "
                        "VALUES (%s,%s)",
                        (new_riga_id, giorno),
                    )
            after_lines.append({
                "varieta": line["varieta"], "quantita": line["quantita"],
                "tipo_ricorrenza": line["tipo_ricorrenza"],
                "intervallo_giorni": line["intervallo_giorni"],
                "giorni_iso": line["giorni_iso"],
            })

        before = {"numero_versione": numero_versione, "stato": stato_corrente}
        after = {"numero_versione": new_version, "stato": spec["target_stato"], "righe": after_lines}
        cur.execute(
            """INSERT INTO tpo.audit_eventi
               (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                before_data,after_data,correlation_id,provenance)
               VALUES (%s,%s,'PROGRAMMA_FORNITURA',%s,'UPDATE',%s,%s,%s,%s,%s)""",
            (now, ACTOR, pf_pid, spec["reason"], Jsonb(before), Jsonb(after),
             f"PROGRAMMA-FORNITURA-REVISIONE-2026-10-02-{pf_pid}",
             "OWNER_AUTHORIZED_REVISION_2026-10-02"),
        )
        conn.commit()
        print(f"OK: {nome} {pf_pid} v{numero_versione} -> v{new_version} ({spec['target_stato']}).")
    print()


def sospendi_margot(conn):
    print("=== Margot (PF-000006) -- sospensione a tempo indeterminato ===")
    with conn.cursor() as cur:
        cur.execute(
            """SELECT pv.numero_versione, pv.stato
               FROM tpo.programmi_fornitura p
               JOIN tpo.programmi_fornitura_versioni pv ON pv.programma_fornitura_id=p.id
               WHERE p.public_id='PF-000006' AND pv.valida_al IS NULL AND pv.voided_at IS NULL"""
        )
        numero_versione, stato = cur.fetchone()
    if stato == "SOSPESO":
        print(f"Margot e' gia' SOSPESO (v{numero_versione}). Salto.")
        print()
        return
    effective_at = datetime.now(timezone.utc).isoformat()
    result = subprocess.run([
        RUN, "programma-fornitura", "sospendi",
        "--programma", "PF-000006",
        "--expected-numero-versione", str(numero_versione),
        "--effective-at", effective_at,
        "--actor", ACTOR,
        "--reason", "Richiesta Matteo 2/10/2026: Margot sospeso a tempo indeterminato.",
        "--correlation-id", "PROGRAMMA-FORNITURA-SOSPENDI-2026-10-02-MARGOT",
        "--idempotency-key", "SOSPENDI-MARGOT-2026-10-02-001",
        "--confirm",
    ], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit("FALLITO: sospensione Margot")
    print("OK: Margot sospeso a tempo indeterminato.")
    print()


conn = db()
try:
    for spec in REVISIONS:
        try:
            revisiona(conn, spec)
        except SystemExit as exc:
            conn.rollback()
            print(f"FERMO per {spec['nome']}: {exc}")
            print()
    try:
        sospendi_margot(conn)
    except SystemExit as exc:
        conn.rollback()
        print(f"FERMO per Margot: {exc}")
finally:
    conn.close()

print("=== FATTO ===")
