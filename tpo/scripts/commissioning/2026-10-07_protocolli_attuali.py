"""SOLA LETTURA - protocolli agronomici APPROVATI correnti per varieta': tempi di produzione usati dal planner.

Per ogni varieta': versione di protocollo, giorni di germinazione e di luce/crescita (=> giorni dalla semina al
"pronto"), anticipo di raccolta (lead min/max prima della consegna), ciclo totale semina -> consegna, grammi per SET,
resa, granularita'. Da confrontare con i tempi REALI: se la realta' e' diversa, si crea una nuova versione di
protocollo con il comando governato `tpo protocollo commission`; le semine gia' fatte tengono la versione con cui
sono state seminate. Non scrive nulla.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-07_protocolli_attuali.py
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

SQL = """
SELECT v.denominazione, pv.public_id, pv.numero_versione, pv.valida_dal, pv.idratazione_ore,
       pv.germinazione_giorni, pv.crescita_luce_giorni, pv.harvest_min_lead_giorni, pv.harvest_max_lead_giorni,
       pv.buffer_temporale_minuti, pv.ciclo_produttivo_nominale_giorni, pv.grammi_seme_per_set, pv.resa_attesa, pv.resa_unita_misura::text,
       pv.granularita_produttiva, pv.orario_semina_previsto, pv.orario_raccolta_target
FROM tpo.protocollo_versioni pv
JOIN tpo.protocolli p ON p.id = pv.protocollo_id
JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id
JOIN tpo.cultivar c ON c.id = cu.cultivar_id
JOIN tpo.varieta v ON v.id = c.varieta_id
JOIN tpo.usi_produttivi up ON up.id = cu.uso_produttivo_id AND up.codice = 'MICROGREEN'
WHERE pv.stato_approvazione = 'APPROVATA' AND pv.valida_al IS NULL
ORDER BY v.denominazione"""


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


def run(conn, out=print) -> int:
    cur = conn.cursor()
    cur.execute(SQL)
    out("== PROTOCOLLI APPROVATI CORRENTI (NULLA E' STATO SCRITTO)")
    out("varieta | versione | valida dal | idratazione h | germinazione gg | luce/crescita gg | semina->pronto gg | "
        "lead raccolta min-max gg | ciclo semina->consegna gg | buffer min | g/SET | resa | granularita' | "
        "ore semina / raccolta")
    for (name, pid, number, valid_from, hydration, germ, light, lmin, lmax, buffer, nominal, gps, yld, uom, gran,
         sow_time, harvest_time) in cur.fetchall():
        ready = int(germ) + int(light)
        hyd = _n(hydration) if hydration is not None else '-'
        out(f"{name} | {pid} (v{number}) | {valid_from:%Y-%m-%d} | {hyd} | {germ} | {light} | {ready} | "
            f"{lmin}-{lmax} | {ready + int(lmin)} (nominale {nominal}) | {buffer or 0} | {_n(gps)} | {_n(yld)} {uom} | {_n(gran)} | "
            f"{sow_time} / {harvest_time}")
    return 0


def main() -> int:
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"],
                           connect_timeout=p["connect_timeout"], autocommit=True)
    conn.read_only = True
    try:
        return run(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
