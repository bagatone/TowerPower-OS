"""Diagnostica di sola lettura: tutti i campi dei protocolli STANDARD gia'
approvati, da usare come riferimento concreto per compilare i parametri
mancanti dei nuovi protocolli Rucola/Pak Choi (nessun dato copiato alla
cieca, solo da mostrare a Matteo come esempio reale)."""
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
            """SELECT v.denominazione, pv.public_id, pv.idratazione_ore,
                      pv.orario_semina_previsto, pv.orario_raccolta_target,
                      pv.germinazione_giorni, pv.crescita_luce_giorni,
                      pv.grammi_seme_per_set, pv.resa_attesa, pv.resa_unita_misura,
                      pv.granularita_produttiva, pv.harvest_min_lead_giorni,
                      pv.harvest_max_lead_giorni, pv.buffer_temporale_minuti
               FROM tpo.protocollo_versioni pv
               JOIN tpo.protocolli p ON p.id = pv.protocollo_id
               JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id
               JOIN tpo.cultivar c ON c.id = cu.cultivar_id
               JOIN tpo.varieta v ON v.id = c.varieta_id
               WHERE pv.stato_approvazione = 'APPROVATA'
               ORDER BY v.denominazione"""
        )
        for row in cur.fetchall():
            (nome, pid, idrat, semina_t, raccolta_t, germ, luce, grammi, resa, resa_uom,
             gran, hmin, hmax, buffer) = row
            print(
                f"{nome} ({pid}): idratazione={idrat}h semina_prevista={semina_t} "
                f"raccolta_target={raccolta_t} germinazione={germ}gg luce={luce}gg "
                f"grammi/set={grammi} resa_attesa={resa}{resa_uom.lower()}/set "
                f"granularita={gran} harvest_lead={hmin}-{hmax}gg buffer={buffer}min"
            )
finally:
    conn.close()
