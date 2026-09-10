"""Lookup di sola lettura: SEM-ID/version rucola aperte + programma_fornitura Abalus.

Serve a raccogliere gli identificatori reali necessari per:
  - `tpo semina transition` (scarto rucola)
  - una eventuale correzione del programma di fornitura Abalus

Non scrive nulla sul database. Esegui con:
  .venv/bin/python scripts/commissioning/2026-09-10_lookup_rucola_abalus.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402

parameters = load_postgresql_parameters()
os.environ["TPO_DATABASE_HOST"] = parameters["host"]
os.environ["TPO_DATABASE_PORT"] = str(parameters["port"])
os.environ["TPO_DATABASE_NAME"] = parameters["dbname"]
os.environ["TPO_DATABASE_USER"] = parameters["user"]
os.environ["TPO_DATABASE_PASSWORD"] = parameters["password"]
os.environ["TPO_DATABASE_SSLMODE"] = parameters["sslmode"]
os.environ["TPO_DATABASE_CONNECT_TIMEOUT"] = str(parameters["connect_timeout"])

import psycopg  # noqa: E402

from src.tpo_core.application.clienti_lettura.models import RichiediElencoClienti  # noqa: E402
from src.tpo_core.application.fornitura_ordini_consegne_lettura.models import (  # noqa: E402
    RichiediElencoProgrammiFornitura,
)
from src.tpo_core.application.semina_raccolta_lettura.models import (  # noqa: E402
    RichiediElencoSemine,
)
from src.tpo_core.bootstrap import (  # noqa: E402
    build_clienti_lettura_service,
    build_fornitura_ordini_consegne_lettura_service,
    build_semina_raccolta_lettura_service,
)
from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings  # noqa: E402

settings = PostgreSQLSettings.from_environment()

print(f"=== TUTTE LE SEMINE (totale: {len(build_semina_raccolta_lettura_service(settings).elenco(RichiediElencoSemine()).semine)}) ===")
semina_service = build_semina_raccolta_lettura_service(settings)
elenco = semina_service.elenco(RichiediElencoSemine())
rucola_ids = []
for s in elenco.semine:
    hay = f"{s.varieta_denominazione} {s.cultivar_snapshot}".lower()
    is_rucola = "rucola" in hay or "rocket" in hay or "arugula" in hay
    marker = " <-- possibile rucola" if is_rucola else ""
    print(f"  {s.semina_id.value}  stato={s.stato}  varieta={s.varieta_denominazione}  "
          f"cultivar={s.cultivar_snapshot}  data_avvio={s.data_avvio.isoformat()}  "
          f"qty={s.quantita_seme} {s.unita_misura}{marker}")
    if is_rucola and s.stato != "CHIUSA":
        rucola_ids.append(s.semina_id.value)
if not elenco.semine:
    print("  (nessuna semina trovata nel sistema)")

print()
print("=== version (colonna interna, non esposta dal read boundary) ===")
if rucola_ids:
    conn = psycopg.connect(
        host=settings.host, port=settings.port, dbname=settings.database,
        user=settings.user, password=settings.password, sslmode=settings.sslmode,
        connect_timeout=settings.connect_timeout_seconds,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT public_id, version, stato FROM tpo.semine "
                "WHERE public_id = ANY(%s) ORDER BY public_id",
                (rucola_ids,),
            )
            for row in cur.fetchall():
                print(f"  {row[0]}  version={row[1]}  stato={row[2]}")
    finally:
        conn.close()

print()
print("=== TUTTI I CLIENTI ===")
clienti_service = build_clienti_lettura_service(settings)
elenco_clienti = clienti_service.elenco(RichiediElencoClienti())
abalus_ids = []
for c in elenco_clienti.clienti:
    is_abalus = "abalus" in c.denominazione.lower()
    marker = " <-- possibile Abalus" if is_abalus else ""
    print(f"  {c.cliente_id.value}  denominazione={c.denominazione}{marker}")
    if is_abalus:
        abalus_ids.append(c.cliente_id.value)
if not elenco_clienti.clienti:
    print("  (nessun cliente trovato nel sistema)")

print()
print("=== TUTTI I PROGRAMMI DI FORNITURA ===")
fornitura_service = build_fornitura_ordini_consegne_lettura_service(settings)
elenco_programmi = fornitura_service.programmi_fornitura(RichiediElencoProgrammiFornitura())
for p in elenco_programmi.programmi:
    marker = " <-- possibile Abalus" if p.cliente_id.value in abalus_ids else ""
    print(f"  {p.programma_id.value}  cliente={p.cliente_denominazione} ({p.cliente_id.value})  "
          f"versione_corrente={p.numero_versione}  stato={p.stato}  "
          f"valida_dal={p.valida_dal.isoformat()}  righe={len(p.righe)}{marker}")
if not elenco_programmi.programmi:
    print("  (nessun programma di fornitura trovato nel sistema)")
