"""Diagnostica di sola lettura: dettaglio completo dei 9 programmi di
fornitura correnti (orario_generazione, finestra_operativa_giorni,
data_fine, e per ogni riga GIORNI_SETTIMANA i giorni ISO reali) -- serve
come riferimento concreto prima di costruire le revisioni/i nuovi
programmi richiesti da Matteo il 2/10/2026 (Selvaje, Margot, Tagoro,
Azul y Sal, Alchimia, + i 3 nuovi clienti)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

p = load_postgresql_parameters()
conn = psycopg.connect(
    host=p["host"], port=p["port"], dbname=p["dbname"],
    user=p["user"], password=p["password"], sslmode=p["sslmode"],
    connect_timeout=p["connect_timeout"],
)
try:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.public_id, c.denominazione, pf.public_id, pfv.id, pfv.numero_versione,
                      pfv.stato, pfv.data_inizio, pfv.data_fine, pfv.orario_generazione,
                      pfv.finestra_operativa_giorni, pfv.valida_dal
               FROM tpo.clienti c
               JOIN tpo.programmi_fornitura pf ON pf.cliente_id = c.id
               JOIN tpo.programmi_fornitura_versioni pfv
                 ON pfv.programma_fornitura_id = pf.id AND pfv.valida_al IS NULL AND pfv.voided_at IS NULL
               ORDER BY c.denominazione"""
        )
        programmi = cur.fetchall()
        for row in programmi:
            (cli_pid, cli_denom, pf_pid, pfv_id, numero, stato, data_inizio, data_fine,
             orario_gen, finestra, valida_dal) = row
            print(f"{cli_denom} ({cli_pid}) -- {pf_pid} v{numero} {stato}")
            print(f"    data_inizio={data_inizio} data_fine={data_fine} orario_generazione={orario_gen} "
                  f"finestra_operativa_giorni={finestra} valida_dal={valida_dal}")
            cur.execute(
                """SELECT rpf.id, v.public_id, v.denominazione, rpf.quantita, rpf.unita_misura,
                          rpf.tipo_ricorrenza, rpf.intervallo_giorni, rpf.posizione
                   FROM tpo.righe_programma_fornitura rpf
                   JOIN tpo.varieta v ON v.id = rpf.varieta_id
                   WHERE rpf.programma_versione_id = %s ORDER BY rpf.posizione""",
                (pfv_id,),
            )
            for (riga_id, v_pid, v_denom, quantita, unita, tipo_ric, intervallo, posizione) in cur.fetchall():
                giorni_str = ""
                if tipo_ric == "GIORNI_SETTIMANA":
                    cur.execute(
                        "SELECT giorno_iso FROM tpo.righe_programma_giorni WHERE riga_programma_id = %s ORDER BY giorno_iso",
                        (riga_id,),
                    )
                    giorni = [r[0] for r in cur.fetchall()]
                    giorni_str = f" giorni_iso={giorni}"
                print(f"        [{posizione}] {v_denom} ({v_pid}): {quantita}{unita.lower()} "
                      f"{tipo_ric} intervallo={intervallo}{giorni_str}")
            print()
finally:
    conn.close()
