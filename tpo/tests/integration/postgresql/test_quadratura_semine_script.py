"""La quadratura (sola lettura) gira su PostgreSQL reale con un piano commesso."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_allocation_invalidation import _multi_line_plan
from tests.integration.postgresql.test_order_cancellation import _state
from tests.integration.postgresql.test_order_cancellation import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-05_quadratura_semine.py"


def test_quadratura_runs_read_only(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    before = _state(engine)
    spec = importlib.util.spec_from_file_location("quadratura_semine", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    url, lines = engine.url, []
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)
    assert module.run(conn, out=lines.append) == 0
    conn.close()
    text = "\n".join(lines)
    assert "QUADRO PER VARIETA'" in text and "SEMINE IN CORSO" in text and "DA SEMINARE" in text
    assert _state(engine) == before
