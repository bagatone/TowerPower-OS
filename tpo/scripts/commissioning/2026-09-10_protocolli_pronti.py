"""Elenco di sola lettura: le versioni di protocollo gia' pronte (varieta ->
cultivar -> cultivar_uso -> protocollo -> protocollo_versione completi),
con stato di approvazione. Uso:
  .venv/bin/python scripts/commissioning/2026-09-10_protocolli_pronti.py
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402

import psycopg  # noqa: E402

parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
today = date.today()
try:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT v.public_id, v.denominazione, c.denominazione, u.denominazione,
                   p.denominazione, p.tipo, p.attivo,
                   pv.public_id, pv.numero_versione, pv.stato_approvazione,
                   pv.valida_dal, pv.valida_al
            FROM tpo.protocollo_versioni pv
            JOIN tpo.protocolli p ON p.id = pv.protocollo_id
            JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id
            JOIN tpo.cultivar c ON c.id = cu.cultivar_id
            JOIN tpo.varieta v ON v.id = c.varieta_id
            JOIN tpo.usi_produttivi u ON u.id = cu.uso_produttivo_id
            ORDER BY v.public_id
        """)
        for (var_id, var_den, cult_den, uso_den, prot_den, prot_tipo, prot_attivo,
             pv_id, pv_num, pv_stato, pv_dal, pv_al) in cur.fetchall():
            valido_oggi = pv_dal <= today and (pv_al is None or pv_al > today)
            pronto = pv_stato == "APPROVATA" and prot_tipo == "STANDARD" and prot_attivo and valido_oggi
            print(f"{var_id} {var_den} / cultivar={cult_den} / uso={uso_den}")
            print(f"    protocollo '{prot_den}' (tipo={prot_tipo}, attivo={prot_attivo})")
            print(f"    versione {pv_id} v{pv_num}  stato={pv_stato}  valida_dal={pv_dal}  "
                  f"valida_al={pv_al}  [{'PRONTO PER SEMINA' if pronto else 'non pronto'}]")
finally:
    conn.close()
