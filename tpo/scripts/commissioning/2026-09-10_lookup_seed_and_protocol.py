"""Lookup di sola lettura: per ogni LOTTO_SEME con quantita' residua, mostra
le varieta'/protocolli per cui e' realmente commissionabile con
`tpo semina commission` adesso, replicando le precondizioni reali controllate
da infrastructure/postgresql/semina_commissioning.py::_context (approvazione
protocollo, validita' temporale, stato varieta/cultivar/uso, raccomandazione
semente_impieghi, codice di tracciabilita'). Colonne verificate via
information_schema (non dalle migrazioni) per evitare altri errori di nome.

Uso: .venv/bin/python scripts/commissioning/2026-09-10_lookup_seed_and_protocol.py
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
        print("=== LOTTI SEME disponibili (quantita' residua > 0) ===")
        cur.execute("""
            SELECT l.public_id, l.version, s.fornitore, s.referenza_commerciale,
                   l.quantita_residua, l.unita_misura, s.attiva, l.id, s.id
            FROM tpo.lotti_seme l
            JOIN tpo.sementi s ON s.id = l.semente_id
            WHERE l.quantita_residua > 0
            ORDER BY l.public_id
        """)
        lotti = cur.fetchall()
        for row in lotti:
            print(" ", row[:-2])
        if not lotti:
            print("  (nessun lotto con quantita' residua)")

        print()
        print("=== per ogni lotto: cultivar_uso raccomandati + protocollo attivo/approvato ===")
        for (lotto_public_id, _v, fornitore, referenza, _q, _u, semente_attiva,
             _lotto_pk, semente_pk) in lotti:
            cur.execute("""
                SELECT v.public_id, v.denominazione, c.denominazione, u.denominazione,
                       si.raccomandazione, v.stato, c.stato, u.attivo, v.codice_tracciabilita
                FROM tpo.semente_impieghi si
                JOIN tpo.cultivar_usi cu ON cu.id = si.cultivar_uso_id
                JOIN tpo.cultivar c ON c.id = cu.cultivar_id
                JOIN tpo.varieta v ON v.id = c.varieta_id
                JOIN tpo.usi_produttivi u ON u.id = cu.uso_produttivo_id
                WHERE si.semente_id = %s
                ORDER BY v.public_id
            """, (semente_pk,))
            impieghi = cur.fetchall()
            label = f"{lotto_public_id} ({fornitore} / {referenza}, semente.attiva={semente_attiva})"
            if not impieghi:
                print(f"  {label}: nessun impiego/raccomandazione registrato")
                continue
            for (var_id, var_den, cult_den, uso_den, racc, var_stato, cult_stato,
                 uso_attivo, codice_tracc) in impieghi:
                ok = (racc in ("RACCOMANDATA", "UTILIZZABILE") and var_stato == "ATTIVA"
                      and cult_stato == "ATTIVA" and uso_attivo and codice_tracc is not None
                      and semente_attiva)
                marker = "OK" if ok else "NON PRONTO"
                print(f"  {label} -> {var_id} {var_den} / {cult_den} / {uso_den}  "
                      f"raccomandazione={racc}  varieta.stato={var_stato}  cultivar.stato={cult_stato}  "
                      f"uso.attivo={uso_attivo}  codice_tracciabilita={codice_tracc}  [{marker}]")
                if not ok:
                    continue
                cur.execute("""
                    SELECT pv.public_id, pv.numero_versione, pv.stato_approvazione,
                           pv.valida_dal, pv.valida_al, p.tipo, p.attivo
                    FROM tpo.protocollo_versioni pv
                    JOIN tpo.protocolli p ON p.id = pv.protocollo_id
                    JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id
                    JOIN tpo.cultivar c ON c.id = cu.cultivar_id
                    WHERE c.denominazione = %s
                    ORDER BY pv.public_id
                """, (cult_den,))
                protocolli = cur.fetchall()
                if not protocolli:
                    print(f"      (nessuna versione di protocollo trovata per cultivar {cult_den})")
                for pv_id, pv_num, pv_stato, pv_dal, pv_al, p_tipo, p_attivo in protocolli:
                    valido_oggi = pv_dal <= today and (pv_al is None or pv_al > today)
                    pronto = (pv_stato == "APPROVATA" and p_tipo == "STANDARD"
                              and p_attivo and valido_oggi)
                    print(f"      protocollo {pv_id} v{pv_num}  stato={pv_stato}  tipo={p_tipo}  "
                          f"attivo={p_attivo}  valida_dal={pv_dal}  valida_al={pv_al}  "
                          f"valido_oggi={valido_oggi}  [{'PRONTO' if pronto else 'non pronto'}]")
finally:
    conn.close()
