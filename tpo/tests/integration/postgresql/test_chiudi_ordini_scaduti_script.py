"""Il comando operativo di Matteo (anteprima / --esegui) sul PostgreSQL reale di prova."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_allocation_invalidation import _multi_line_plan, _scalar
from tests.integration.postgresql.test_order_cancellation import _state
from tests.integration.postgresql.test_order_cancellation import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-05_chiudi_ordini_scaduti.py"


def _module():
    spec = importlib.util.spec_from_file_location("chiudi_ordini_scaduti", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def test_preview_writes_nothing_then_execute_closes_only_expired(planning_database):
    engine = planning_database
    _multi_line_plan(engine)                       # ORD-1 15/8, ORD-2 12/8, ORD-3 13/8, ORD-4 14/8
    module, lines, before = _module(), [], _state(engine)
    cutoff = date(2026, 8, 14)

    conn = _connect(engine)
    assert module.run(conn, cutoff, False, out=lines.append) == 0
    conn.close()
    text = "\n".join(lines)
    assert "ORDINI CHE VERRANNO ANNULLATI (2)" in text and "ANTEPRIMA: nulla e' stato scritto" in text
    assert "NON TOCCATI: ordini con consegna prevista dal 2026-08-14 in poi: 2" in text
    assert _state(engine) == before

    lines.clear()
    conn = _connect(engine)
    assert module.run(conn, cutoff, True, out=lines.append) == 0
    conn.close()
    assert "FATTO: 2 ordini ANNULLATI" in "\n".join(lines)
    assert _scalar(engine, "SELECT count(*) FROM tpo.ordini WHERE stato='ANNULLATO'") == 2

    lines.clear()                                  # seconda esecuzione: niente piu' da chiudere, nulla cambia
    after = _state(engine)
    conn = _connect(engine)
    assert module.run(conn, cutoff, True, out=lines.append) == 0
    conn.close()
    assert "Nessun ordine da chiudere" in "\n".join(lines) and _state(engine) == after
