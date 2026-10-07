"""SOLA LETTURA - non scrive nulla. Simula cosa succederebbe se il planner vedesse le semine fisiche in corso.

Oggi le semine registrate hanno resa attesa e finestra di raccolta VUOTE: il planner non le conta e propone
di riseminare quasi tutto. Prima di riempire quei campi (decisione di Matteo) questo script mostra, senza toccare nulla:

  1. per ogni semina non chiusa, i valori che DERIVEREBBERO dal protocollo approvato con cui e' stata seminata:
       SET              = intero DICHIARATO (un SET resta un SET): qui proposto solo se i grammi tornano a SET interi
       finestra raccolta = [avvio + giorni germinazione + giorni luce/crescita , + (lead max - lead min) giorni]
       resa attesa      = quella del protocollo (mostrata cosi' com'e', con la sua unita')
  2. per ogni varieta', la prima consegna degli ordini aperti rispetto all'inizio finestra delle semine:
     il planner si FERMA con RESOURCE_NOT_READY ("SEMINA non eleggibile entro la consegna") se una semina con la
     finestra compilata inizia DOPO la consegna di una domanda della stessa varieta'. Le varieta' a rischio sono
     segnate "BLOCCO PLANNER".

Uso (dalla cartella del progetto):
    .venv/bin/python scripts/commissioning/2026-10-06_simula_semine_in_corso.py
"""
from __future__ import annotations

import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

SEMINE_SQL = """
SELECT s.public_id, v.denominazione, s.stato::text, s.data_avvio, s.quantita_seme, pv.public_id,
       pv.grammi_seme_per_set, pv.resa_attesa, pv.resa_unita_misura::text,
       pv.germinazione_giorni, pv.crescita_luce_giorni, pv.harvest_min_lead_giorni, pv.harvest_max_lead_giorni,
       pv.buffer_temporale_minuti,
       s.expected_useful_quantity IS NOT NULL
FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
JOIN tpo.protocollo_versioni pv ON pv.id=s.protocollo_versione_id
WHERE s.stato<>'CHIUSA' AND s.unita_misura='GRAM'
ORDER BY v.denominazione, s.data_avvio, s.public_id"""

DOMANDA_SQL = """
SELECT v.denominazione, MIN(o.data_consegna_prevista), COUNT(DISTINCT o.id),
       SUM(ro.quantita - COALESCE((SELECT SUM(rc.quantita) FROM tpo.righe_consegna rc
            JOIN tpo.consegne c ON c.id=rc.consegna_id
            WHERE rc.riga_ordine_id=ro.id AND c.stato='CONSEGNATA'),0))
FROM tpo.righe_ordine ro JOIN tpo.ordini o ON o.id=ro.ordine_id JOIN tpo.varieta v ON v.id=ro.varieta_id
WHERE o.stato IN ('APERTO','PARZIALMENTE_EVASO') AND ro.unita_misura='SET'
GROUP BY v.denominazione ORDER BY 1"""


def simulate(conn, out=print) -> int:
    cur = conn.cursor()
    cur.execute(SEMINE_SQL)
    rows = cur.fetchall()
    cur.execute(DOMANDA_SQL)
    demand = {r[0]: (r[1], r[2], Decimal(r[3])) for r in cur.fetchall()}

    out("== SEMINE IN CORSO: valori che deriverebbero dal protocollo (NULLA E' STATO SCRITTO)")
    out("semina | varieta | stato | avvio | SET | resa protocollo | finestra raccolta (derivata) | gia' compilata")
    starts: dict[str, list] = {}
    for (pid, nome, stato, avvio, grams, pv, gps, resa, resa_uom, germ, luce, lmin, lmax, buf, filled) in rows:
        ratio = Decimal(grams) / Decimal(gps)
        n_set = f"{int(ratio)}" if ratio == ratio.to_integral_value() and ratio >= 1 else "da dichiarare"
        ready = avvio + timedelta(days=int(germ) + int(luce), minutes=int(buf or 0))
        end = ready + timedelta(days=int(lmax) - int(lmin))
        starts.setdefault(nome, []).append((pid, ready))
        out(f"{pid} | {nome} | {stato} | {avvio:%Y-%m-%d} | {n_set} | {resa} {resa_uom} (protocollo {pv}) | "
            f"{ready:%Y-%m-%d} -> {end:%Y-%m-%d} | {'si' if filled else 'no'}")

    out("\n== RISCHIO PER VARIETA': prima consegna degli ordini aperti vs inizio finestra delle semine")
    out("varieta | domanda aperta (SET) | ordini | prima consegna | semine che iniziano DOPO la prima consegna | esito")
    blocked = 0
    for nome in sorted(set(demand) | set(starts)):
        if nome not in demand:
            continue
        first, n_orders, qty = demand[nome]
        late = [pid for pid, ready in starts.get(nome, []) if ready.date() > first]
        verdict = "BLOCCO PLANNER" if late else "ok"
        blocked += bool(late)
        out(f"{nome} | {qty} | {n_orders} | {first} | {', '.join(late) or '-'} | {verdict}")

    out("\nLettura: 'BLOCCO PLANNER' = se compilassimo la finestra di quelle semine, il planner si fermerebbe con "
        "RESOURCE_NOT_READY finche' esistono ordini con consegna prima dell'inizio della finestra. "
        "Prima di compilare servirebbe quindi anche una regola del planner (saltare la semina non ancora pronta "
        "invece di fermarsi), oppure compilare solo le semine che iniziano entro la prima consegna.")
    out("Le date sono DERIVATE dal protocollo (non misurate): le semine in luce/crescita reali possono differire.")
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
        return simulate(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
