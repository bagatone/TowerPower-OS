"""Il comando operativo di Matteo (anteprima / --esegui) sul PostgreSQL reale di prova."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_allocation_invalidation import (
    STOCK, _multi_line_plan, _scalar, _sold_outside_the_system, _snapshot,
)
from tests.integration.postgresql.test_allocation_invalidation import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-05_invalida_stock_obsoleto.py"


def _module():
    spec = importlib.util.spec_from_file_location("invalida_stock_obsoleto", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def test_preview_writes_nothing_and_execute_invalidates(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    _sold_outside_the_system(engine)
    module, lines = _module(), []
    before = _snapshot(engine)

    conn = _connect(engine)
    assert module.run(conn, STOCK, False, out=lines.append) == 0
    conn.close()
    text = "\n".join(lines)
    assert "ANTEPRIMA: nulla e' stato scritto" in text and "| 3.000000 | 3.000000 SET" in text
    assert _scalar(engine, "SELECT count(*) FROM tpo.transizioni_allocazione") == 0
    assert _snapshot(engine) == before

    lines.clear()
    conn = _connect(engine)
    assert module.run(conn, STOCK, True, out=lines.append) == 0
    conn.close()
    assert "FATTO: 3 allocazioni invalidate" in "\n".join(lines)
    assert _scalar(engine, "SELECT count(*) FROM tpo.allocazioni WHERE state='INVALIDA'") == 3
    assert _snapshot(engine) == before

    lines.clear()                                    # seconda esecuzione: rifiutata, nulla cambia
    conn = _connect(engine)
    assert module.run(conn, STOCK, True, out=lines.append) == 2
    conn.close()
    assert "RIFIUTATO" in "\n".join(lines)
    assert _scalar(engine, "SELECT count(*) FROM tpo.transizioni_allocazione") == 3
