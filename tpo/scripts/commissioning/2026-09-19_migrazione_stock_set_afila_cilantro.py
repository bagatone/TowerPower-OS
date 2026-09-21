"""Migrazione una tantum (Owner Decision Matteo 19/9/2026: "o facciamo tutto
in grammi o tutto in set" -- vedi docs/architecture/
STOCK_UNITA_VENDITA_INTERA_PROPOSTA.md e migrations/versions/
20260919_0035_stock_unita_composita.py) per portare lo STOCK vivo di Afila e
Cilantro da GRAM a SET, senza mai riscrivere la storia.

Tentativo precedente (prima di questa versione dello script): un semplice
UPDATE della riga STOCK esistente da GRAM a SET e' fallito con
ForeignKeyViolation, perche' tpo.movimenti_magazzino ha una foreign key
RESTRICT verso tpo.stock.(varieta_id,unita_misura) e i 4 MOVIMENTI storici
in GRAM (MOV-000001..4) la referenziano ancora -- quella riga non puo' mai
essere aggiornata/cancellata. La migrazione 20260919_0035 ha rilassato la
chiave di tpo.stock a (varieta_id,unita_misura), quindi ora e' possibile
avere due righe per la stessa VARIETA: questo script NON tocca la riga GRAM
esistente se non per azzerarne la disponibile (nessun cambio di unita_misura,
nessun conflitto di foreign key), e ne crea una nuova in SET.

Afila (SEM-000002): 933g GRAM (congelata a 0) -> nuova riga 3 SET (311g/SET
Callao 18/9 + 622g/SET Selvaje 17/9, vedi RAC-000001/RAC-000003,
MOV-000001/MOV-000003).
Cilantro (SEM-000001): 408g GRAM (congelata a 0) -> nuova riga 2 SET
(204g/SET Azul y Sal 18/9 + 204g/SET Selvaje 17/9, vedi RAC-000002/
RAC-000004, MOV-000002/MOV-000004).

Non tocca in alcun modo tpo.raccolte o tpo.movimenti_magazzino: la storia
dei 4 eventi reali di raccolta+carico in GRAM resta cosi' come registrata.
La riga STOCK in GRAM resta scritta per sempre (non viene cancellata --
non si puo', ed e' comunque un artefatto storico legittimo), ma diventa
un residuo congelato a disponibile=0, mai piu' toccato da nessuna parte
viva del sistema da questo momento in poi.

Guardie di sicurezza: la disponibile GRAM attuale deve corrispondere
esattamente al valore atteso (933 / 408) prima di procedere, e non deve
esistere gia' una riga SET per la stessa VARIETA -- altrimenti lo script si
ferma senza scrivere nulla (evita sia di sovrascrivere alla cieca uno stato
cambiato nel frattempo, sia di duplicare una riga SET se lo script viene
rieseguito per errore).
"""
import sys, json
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)

ACTOR = "giulia"
CORRELATION_ID = "STOCK-MIGRAZIONE-SET-2026-09-19-AFILA-CILANTRO"
PROVENANCE = "OWNER_AUTHORIZED_CORRECTION_2026-09-19"
FREEZE_REASON = (
    "Congelamento una tantum della riga STOCK storica in GRAM (Owner "
    "Decision Matteo 19/9/2026, 'o facciamo tutto in grammi o tutto in "
    "set'; migrations/versions/20260919_0035_stock_unita_composita.py): "
    "i 4 MOVIMENTI_MAGAZZINO storici in GRAM (MOV-000001..4) referenziano "
    "questa riga con una foreign key RESTRICT e non possono mai essere "
    "riscritti, quindi la riga stessa non puo' mai cambiare unita' di "
    "misura -- resta scritta per sempre come residuo storico, azzerata e "
    "mai piu' toccata da nessuna parte viva del sistema da oggi in poi."
)
CREATE_REASON = (
    "Creazione una tantum della riga STOCK viva in SET (stessa Owner "
    "Decision del congelamento GRAM sopra): i microgreens vengono venduti "
    "come SET intero, mai tagliati/pesati. Quantita' SET identica a quella "
    "gia' raccolta (nessun fattore di resa, nessun numero nuovo inventato). "
    "RACCOLTE e MOVIMENTI_MAGAZZINO storici in GRAM restano invariati."
)

# semina pubblica -> (nome, GRAM atteso attuale, SET da creare)
TARGETS = (
    ("SEM-000002", "Afila", Decimal("933"), Decimal("3")),
    ("SEM-000001", "Cilantro", Decimal("408"), Decimal("2")),
)

try:
    with conn.cursor() as cur:
        results = []
        for semina_public_id, nome, expected_gram, new_set_qty in TARGETS:
            cur.execute(
                """SELECT v.id, v.public_id FROM tpo.semine s
                   JOIN tpo.varieta v ON v.id = s.varieta_id
                   WHERE s.public_id = %s""",
                (semina_public_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise SystemExit(f"SEMINA {semina_public_id} ({nome}) non trovata.")
            varieta_pk, varieta_public_id = row

            cur.execute(
                """SELECT disponibile, version FROM tpo.stock
                   WHERE varieta_id = %s AND unita_misura = 'GRAM' FOR UPDATE""",
                (varieta_pk,),
            )
            gram_row = cur.fetchone()
            if gram_row is None:
                raise SystemExit(f"STOCK GRAM per {nome} ({varieta_public_id}) non trovato.")
            disponibile_prima, gram_version = gram_row
            disponibile_prima = Decimal(disponibile_prima)
            if disponibile_prima != expected_gram:
                raise SystemExit(
                    f"STOCK GRAM {nome} ({varieta_public_id}) disponibile attuale "
                    f"{disponibile_prima}g diverso dall'atteso {expected_gram}g: "
                    "lo stato e' cambiato nel frattempo, mi fermo senza scrivere. "
                    "Verificare manualmente prima di ripetere."
                )

            cur.execute(
                "SELECT 1 FROM tpo.stock WHERE varieta_id = %s AND unita_misura = 'SET'",
                (varieta_pk,),
            )
            if cur.fetchone() is not None:
                raise SystemExit(
                    f"STOCK SET per {nome} ({varieta_public_id}) esiste gia': "
                    "questo script sembra gia' stato eseguito, mi fermo senza "
                    "scrivere per non duplicare la riga."
                )

            now = datetime.now(timezone.utc)

            # 1. Congela la riga GRAM esistente: solo disponibile->0, mai
            #    unita_misura (nessuna FK la referenzia su quella colonna
            #    in modo bloccante finche' non cambia il valore).
            cur.execute(
                """UPDATE tpo.stock SET disponibile=0, updated_at=%s, version=version+1
                   WHERE varieta_id=%s AND unita_misura='GRAM' AND version=%s""",
                (now, varieta_pk, gram_version),
            )
            if cur.rowcount != 1:
                raise SystemExit(
                    f"Conflitto di versione su STOCK GRAM {nome} ({varieta_public_id}), "
                    "riprovare (qualcuno ha modificato lo stock nel frattempo)."
                )

            # 2. Crea la nuova riga SET viva.
            cur.execute(
                """INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at,version)
                   VALUES (%s,%s,'SET',%s,0)
                   ON CONFLICT (varieta_id,unita_misura) DO NOTHING""",
                (varieta_pk, new_set_qty, now),
            )
            if cur.rowcount != 1:
                raise SystemExit(
                    f"Riga STOCK SET per {nome} ({varieta_public_id}) non creata "
                    "(conflitto concorrente): riprovare."
                )

            before_gram = {"disponibile": str(disponibile_prima), "unita_misura": "GRAM"}
            after_gram = {"disponibile": "0", "unita_misura": "GRAM"}
            cur.execute(
                """INSERT INTO tpo.audit_eventi
                     (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                      before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'STOCK',%s,'CORRECTION',%s,%s::jsonb,%s::jsonb,%s,%s)""",
                (now, ACTOR, varieta_public_id, FREEZE_REASON, json.dumps(before_gram),
                 json.dumps(after_gram), CORRELATION_ID, PROVENANCE),
            )
            after_set = {"disponibile": str(new_set_qty), "unita_misura": "SET"}
            cur.execute(
                """INSERT INTO tpo.audit_eventi
                     (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                      before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,'STOCK',%s,'INSERT',%s,NULL,%s::jsonb,%s,%s)""",
                (now, ACTOR, varieta_public_id, CREATE_REASON, json.dumps(after_set),
                 CORRELATION_ID, PROVENANCE),
            )
            results.append((nome, varieta_public_id, disponibile_prima, new_set_qty))

        conn.commit()
        for nome, varieta_public_id, prima_gram, nuova_set in results:
            print(f"OK: {nome} ({varieta_public_id}) STOCK GRAM {prima_gram}g -> 0g "
                  f"(congelato), nuova riga SET {nuova_set} creata.")
except SystemExit:
    conn.rollback()
    raise
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
