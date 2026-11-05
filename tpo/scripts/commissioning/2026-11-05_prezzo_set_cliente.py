"""PREZZO PER SET DEL CLIENTE (5/11/2026, richiesta di Matteo: Salvaje, 3 SET devono fare 40,00 EUR).

  .venv/bin/python scripts/commissioning/2026-11-05_prezzo_set_cliente.py CLI-000004 13.3333            # anteprima
  .venv/bin/python scripts/commissioning/2026-11-05_prezzo_set_cliente.py CLI-000004 13.3333 --esegui   # scrive davvero

Cambia SOLO tpo.dati_fiscali_cliente.prezzo_set_fattura del cliente (il prezzo per SET che sostituisce il listino su bolle e
fatture GENERATE DOPO). Non tocca listino, ordini, consegne, fatture gia' emesse. Evento di audit con prezzo prima/dopo e
comando correttivo stampato. Il cliente deve avere gia' i dati fiscali (esiste la riga).
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
ACTOR = "matteo"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cliente", help="codice cliente, es. CLI-000004")
    ap.add_argument("prezzo", help="EUR per SET, es. 13.3333")
    ap.add_argument("--esegui", action="store_true")
    a = ap.parse_args()
    try:
        nuovo = Decimal(a.prezzo.replace(",", "."))
        if nuovo <= 0 or nuovo.as_tuple().exponent < -4:
            raise InvalidOperation
    except InvalidOperation:
        print("STOP: prezzo non valido (positivo, al massimo 4 decimali)."); return 2
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        cur = conn.cursor()
        cur.execute("""SELECT c.id, c.denominazione, d.prezzo_set_fattura FROM tpo.clienti c
                       LEFT JOIN tpo.dati_fiscali_cliente d ON d.cliente_id = c.id WHERE c.public_id = %s""", (a.cliente,))
        r = cur.fetchone()
        if r is None:
            print(f"STOP: cliente {a.cliente} non trovato."); return 2
        cid, nome, prima = r
        cur.execute("SELECT 1 FROM tpo.dati_fiscali_cliente WHERE cliente_id = %s", (cid,))
        if cur.fetchone() is None:
            print(f"STOP: {nome} non ha dati fiscali registrati: nulla da aggiornare."); return 2
        print(f"{nome} ({a.cliente}): prezzo per SET {prima if prima is not None else 'listino'} -> {nuovo}")
        for n in (1, 2, 3, 6):
            print(f"  {n} SET = {(n * nuovo).quantize(Decimal('0.01'))} EUR")
        if prima is not None and Decimal(prima) == nuovo:
            print("Gia' cosi': non cambio nulla."); return 0
        if not a.esegui:
            print("\nANTEPRIMA: nulla scritto. Per scrivere: stesso comando con --esegui."); return 0
        cur.execute("UPDATE tpo.dati_fiscali_cliente SET prezzo_set_fattura = %s, updated_at = now(), updated_by = %s "
                    "WHERE cliente_id = %s", (nuovo, ACTOR, cid))
        cur.execute(
            """INSERT INTO tpo.audit_eventi (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                                             before_data,after_data,correlation_id,provenance)
               VALUES (CURRENT_TIMESTAMP,%s,'FATTURA_ESTERNA',%s,'UPDATE',%s,%s::jsonb,%s::jsonb,%s,%s)""",
            (ACTOR, a.cliente, "Prezzo per SET del cliente corretto da Matteo il 5/11/2026 (3 SET = 40,00 EUR)",
             json.dumps({"prezzo_set": None if prima is None else str(prima)}), json.dumps({"prezzo_set": str(nuovo)}),
             f"prezzo-set-cliente-{a.cliente}-{nuovo}", json.dumps({"registro_fatture_esterne": "OWNER_AUTHORIZED"})))
        conn.commit()
        print("\nFATTO.")
        if prima is not None:
            print(f"Comando correttivo: .venv/bin/python scripts/commissioning/2026-11-05_prezzo_set_cliente.py {a.cliente} {prima} --esegui")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
