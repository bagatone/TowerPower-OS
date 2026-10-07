"""Annullamento di ordini indicati esplicitamente (anteprima / --esegui) sul PostgreSQL reale di prova."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_allocation_invalidation import _multi_line_plan, _scalar
from tests.integration.postgresql.test_order_cancellation import _state
from tests.integration.postgresql.test_order_cancellation import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-07_annulla_ordini.py"


def _module():
    spec = importlib.util.spec_from_file_location("annulla_ordini", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def test_preview_writes_nothing_then_execute_cancels_only_the_named_future_orders(planning_database):
    engine = planning_database
    _multi_line_plan(engine)                       # ORD-2 12/8, ORD-3 13/8, ORD-4 14/8, ORD-1 15/8 (tutti futuri rispetto al 2026-08)
    module, lines, before = _module(), [], _state(engine)

    conn = _connect(engine)
    assert module.run(conn, ["ORD-000001", "ORD-000004"], "errati", False, out=lines.append) == 0
    conn.close()
    text = "\n".join(lines)
    assert "ORDINI CHE VERRANNO ANNULLATI (2)" in text and "ANTEPRIMA: nulla e' stato scritto" in text
    assert _state(engine) == before

    lines.clear()
    conn = _connect(engine)
    assert module.run(conn, ["ORD-000001", "ORD-000004"], "errati", True, out=lines.append) == 0
    conn.close()
    assert "FATTO: 2 ordini ANNULLATI" in "\n".join(lines)
    assert _scalar(engine, "SELECT count(*) FROM tpo.ordini WHERE stato='ANNULLATO'") == 2
    assert _scalar(engine, "SELECT count(*) FROM tpo.ordini WHERE stato='ANNULLATO' "
                           "AND public_id IN ('ORD-000001','ORD-000004')") == 2

    lines.clear()                                  # gia' annullati: rifiutato, nulla cambia
    after = _state(engine)
    conn = _connect(engine)
    assert module.run(conn, ["ORD-000001"], "errati", True, out=lines.append) == 2
    conn.close()
    assert "RIFIUTATO" in "\n".join(lines) and _state(engine) == after


def test_unknown_order_is_refused(planning_database):
    lines: list[str] = []
    conn = _connect(planning_database)
    assert _module().run(conn, ["ORD-999999"], "x", True, out=lines.append) == 2
    conn.close()
    assert "STOP" in "\n".join(lines) or "RIFIUTATO" in "\n".join(lines)
