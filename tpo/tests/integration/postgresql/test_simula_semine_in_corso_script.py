"""La simulazione semine in corso e' di sola lettura e gira sullo schema reale."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg

from tests.infrastructure.postgresql.test_production_planning_migrations import (  # noqa: F401
    isolated_postgresql,
)
from tests.integration.postgresql.test_movimento_carico import seeded_raccolta  # noqa: F401
from tests.integration.postgresql.test_raccolta import harvest_environment  # noqa: F401
from tests.integration.postgresql.test_semina_commissioning import environment  # noqa: F401

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-06_simula_semine_in_corso.py"


def _module():
    spec = importlib.util.spec_from_file_location("simula_semine_in_corso", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_simulation_reads_semine_and_writes_nothing(seeded_raccolta):
    engine, _ = seeded_raccolta
    url = engine.url
    with engine.connect() as c:
        before = c.exec_driver_sql("SELECT id, version, expected_useful_quantity, harvest_window_start "
                                   "FROM tpo.semine ORDER BY id").all()
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username, autocommit=True)
    conn.read_only = True
    lines = []
    assert _module().simulate(conn, out=lines.append) == 0
    conn.close()
    text = "\n".join(lines)
    assert "NULLA E' STATO SCRITTO" in text and "RISCHIO PER VARIETA'" in text
    with engine.connect() as c:
        assert c.exec_driver_sql("SELECT id, version, expected_useful_quantity, harvest_window_start "
                                 "FROM tpo.semine ORDER BY id").all() == before
