"""L'elenco dei protocolli approvati correnti (sola lettura) gira su PG reale."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_planning_in_progress_semine import _seed
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-07_protocolli_attuali.py"


def _module():
    spec = importlib.util.spec_from_file_location("protocolli_attuali", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_lists_current_protocol_timings(planning_database):
    engine = planning_database
    _seed(engine, [])
    url = engine.url
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)
    lines: list[str] = []
    assert _module().run(conn, out=lines.append) == 0
    text = "\n".join(lines)
    assert "NULLA E' STATO SCRITTO" in text and "writer test variety" in text.lower() and "PV-" in text
    conn.close()
