"""Situazione consegne (sola lettura) su PostgreSQL reale usa-e-getta."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import psycopg

from tests.infrastructure.postgresql.test_bolla_lettura_reader import _seed_carico_da_raccolta
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    TZ, _seed,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-08_stato_consegne.py"


def _module():
    spec = importlib.util.spec_from_file_location("stato_consegne", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_shows_stock_semine_and_open_orders_and_unknown_client(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _seed(engine, 950001, stock="2", order_quantity="1")
    _seed_carico_da_raccolta(engine, 950001, "1", "TST-0110-D", datetime(2099, 1, 1, 8, tzinfo=TZ))
    url = engine.url
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)
    lines = []
    assert _module().run(conn, ["writer variety 950001"], ["client 950001", "Salvaje"], out=lines.append) == 0
    assert _module().run(conn, ["Inesistente"], [], out=lines.append) == 2
    conn.close()
    text = "\n".join(lines)
    assert "giacenza 2 SET" in text and "SEM-950001" in text and "TST-0110-D" in text
    assert "CLIENTE Writer client 950001" in text and "ORD-950001" in text
    assert "CLIENTE 'Salvaje': NON ESISTE" in text
