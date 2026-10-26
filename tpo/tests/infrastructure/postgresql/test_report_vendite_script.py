"""Report vendite (23/10/2026), su PostgreSQL usa-e-getta: totali per cliente/settimana/varieta', incassato, CSV. Sola lettura."""
from __future__ import annotations

import csv
import importlib.util
import sys
from datetime import date
from pathlib import Path

from tests.infrastructure.postgresql.test_da_incassare_script import _consegna, _paga
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)
from tests.infrastructure.postgresql.test_sposta_giorno_programma_script import _connect

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-23_report_vendite.py"


def _module():
    spec = importlib.util.spec_from_file_location("report_vendite", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _esegui(engine, **kwargs):
    m, righe = _module(), []
    conn = _connect(engine)
    code = m.run(conn, out=righe.append, **kwargs)
    conn.close()
    return code, "\n".join(righe)


def test_totals_paid_unpaid_and_listino_value(writer_postgresql_engine, tmp_path):
    engine = writer_postgresql_engine
    _consegna(engine, 972001, quantita="1", prezzo="12.5")           # 12,50 EUR, da incassare
    _consegna(engine, 972002, quantita="0.5", prezzo="12.5")         # 6,25 EUR, pagata
    _paga(engine, 972002)
    destinazione = tmp_path / "vendite.csv"
    code, testo = _esegui(engine, csv_path=str(destinazione))
    assert code == 0 and "SOLA LETTURA" in testo
    assert "Consegne: 2   Clienti: 2   SET: 1.5" in testo
    assert "Valore al listino: 18.75 EUR  (incassato 6.25 EUR, da incassare 12.50 EUR)" in testo
    assert "Writer client 972001" in testo and "settimana dal" in testo and "Writer variety 972002" in testo
    righe = list(csv.reader(destinazione.open(encoding="utf-8-sig"), delimiter=";"))
    assert righe[0][:5] == ["consegna", "data", "codice_cliente", "cliente", "varieta"] and len(righe) == 3
    per_consegna = {r[0]: r for r in righe[1:]}
    assert per_consegna["CON-972001"][9] == "12.50" and per_consegna["CON-972001"][10] == "no"
    assert per_consegna["CON-972002"][9] == "6.25" and per_consegna["CON-972002"][10] == "si"
    assert per_consegna["CON-972002"][12] == "2099-01-05" and per_consegna["CON-972002"][13] == "CONTANTI"


def test_missing_price_is_stated_and_period_filters(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _consegna(engine, 972003, quantita="1")                          # nessun prezzo
    code, testo = _esegui(engine)
    assert code == 0 and "Listino senza prezzo, valore NON calcolato per: Writer variety 972003" in testo
    assert "Valore al listino: 0.00 EUR" in testo
    code, testo = _esegui(engine, dal=date(2099, 2, 1))
    assert code == 0 and "Nessuna consegna effettuata nel periodo." in testo
    code, testo = _esegui(engine, dal=date(2099, 1, 1), al=date(2099, 1, 1))
    assert "Consegne: 1" in testo
