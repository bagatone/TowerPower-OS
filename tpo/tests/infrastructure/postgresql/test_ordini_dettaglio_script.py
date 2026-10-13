"""Dettaglio ordini con codice di tracciabilita' (sola lettura) su PostgreSQL reale usa-e-getta."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg

from tests.infrastructure.postgresql.test_bolla_lettura_reader import _seed_carico_da_raccolta
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    TZ, _command, _seed, _writer,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-07_ordini_dettaglio.py"


def _module():
    spec = importlib.util.spec_from_file_location("ordini_dettaglio", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def _count(engine, sql):
    with engine.connect() as connection:
        return connection.exec_driver_sql(sql).scalar_one()


def test_undelivered_order_has_no_code_and_shows_lots_and_nothing_is_written(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _seed(engine, 940001, stock="1", order_quantity="1")
    _seed_carico_da_raccolta(engine, 940001, "1", "TST-0110-B", datetime(2099, 1, 1, 8, tzinfo=TZ))
    before = (_count(engine, "SELECT count(*) FROM tpo.movimenti_magazzino"),
              _count(engine, "SELECT count(*) FROM tpo.audit_eventi"))
    lines, conn = [], _connect(engine)
    assert _module().run(conn, ["ORD-940001"], date(2026, 10, 1), out=lines.append) == 0
    conn.close()
    text = "\n".join(lines)
    assert "ORD-940001" in text and "Writer client 940001" in text and "Writer variety 940001" in text
    assert "Consegne registrate: NESSUNA" in text
    assert "TST-0110-B" in text and "SEM-940001" in text        # lotto disponibile con il suo codice
    assert before == (_count(engine, "SELECT count(*) FROM tpo.movimenti_magazzino"),
                      _count(engine, "SELECT count(*) FROM tpo.audit_eventi"))


def test_delivered_order_reports_code_and_untraced_remainder(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _seed(engine, 940002, stock="2", order_quantity="2")
    _seed_carico_da_raccolta(engine, 940002, "1", "TST-0110-C", datetime(2099, 1, 1, 8, tzinfo=TZ))
    _writer(engine).publish(_command(940002, "2", movement=940002))
    lines, conn = [], _connect(engine)
    assert _module().run(conn, ["ORD-940002", "ORD-999999"], date(2026, 10, 1), out=lines.append) == 2
    conn.close()
    text = "\n".join(lines)
    assert "codice TST-0110-C | semina SEM-940002 | raccolta RAC-940002" in text
    assert "senza origine: 1 SET" in text
    assert "ORD-999999: NON TROVATO" in text
