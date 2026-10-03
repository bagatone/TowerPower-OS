"""Diagnostica di sola lettura (nessuna scrittura): elenco di tutti i
clienti con il loro programma di fornitura CORRENTE (se esiste), per avere
un punto della situazione leggibile prima di qualunque correzione --
cosi' si vede insieme cosa dice oggi il database, invece di correggere a
memoria. Un cliente senza programma corrente compare comunque, con
"(nessun programma di fornitura corrente)".

Corretto il 2/10/2026: la join su pfv.valida_al IS NULL mostrava, per
quasi ogni cliente, sia la versione corrente sia quella appena sostituita
(entrambe con valida_al IS NULL finche' non vengono chiuse formalmente
con valida_al, ma quella vecchia ha voided_at impostato). Verificato con
2026-10-02_check_voided_programmi_fornitura.py: NON era un bug nel
sistema reale (l'indice unico uq_programmi_fornitura_versioni_corrente
esclude correttamente le righe voided_at NOT NULL), solo questa query
diagnostica non filtrava voided_at -- stesso genere di falso allarme gia'
verificato ed escluso per il protocollo Hinojo il 19/9. Aggiunto
"AND pfv.voided_at IS NULL" alla condizione di join."""
import sys
from pathlib import Path

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
try:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.public_id, c.denominazione,
                      pf.public_id, pfv.numero_versione, pfv.stato,
                      pfv.data_inizio, pfv.data_fine, pf.data_ripresa_prevista,
                      pfv.id
               FROM tpo.clienti c
               LEFT JOIN tpo.programmi_fornitura pf ON pf.cliente_id = c.id
               LEFT JOIN tpo.programmi_fornitura_versioni pfv
                      ON pfv.programma_fornitura_id = pf.id AND pfv.valida_al IS NULL AND pfv.voided_at IS NULL
               ORDER BY c.denominazione"""
        )
        clienti = cur.fetchall()

        cur.execute(
            """SELECT rpf.programma_versione_id, v.denominazione, rpf.quantita,
                      rpf.unita_misura, rpf.tipo_ricorrenza, rpf.intervallo_giorni, rpf.posizione
               FROM tpo.righe_programma_fornitura rpf
               JOIN tpo.varieta v ON v.id = rpf.varieta_id
               ORDER BY rpf.programma_versione_id, rpf.posizione"""
        )
        righe_per_versione: dict[int, list] = {}
        for row in cur.fetchall():
            righe_per_versione.setdefault(row[0], []).append(row)

    print(f"{len(clienti)} clienti totali\n")
    for (cli_pid, cli_denom, pf_pid, numero_versione, stato, data_inizio,
         data_fine, data_ripresa, pfv_id) in clienti:
        if pf_pid is None:
            print(f"{cli_denom} ({cli_pid}): nessun programma di fornitura corrente")
            continue
        extra = f", ripresa prevista {data_ripresa}" if stato == "SOSPESO" and data_ripresa else ""
        print(
            f"{cli_denom} ({cli_pid}): {pf_pid} v{numero_versione} stato={stato} "
            f"dal {data_inizio}{' al ' + str(data_fine) if data_fine else ''}{extra}"
        )
        for riga in righe_per_versione.get(pfv_id, []):
            (_pfv_id, varieta, quantita, unita, tipo_ric, intervallo, _pos) = riga
            ric = f"ogni {intervallo} giorni" if tipo_ric == "OGNI_X_GIORNI" else tipo_ric
            print(f"    {varieta}: {quantita}{unita.lower()} -- {ric}")
finally:
    conn.close()
