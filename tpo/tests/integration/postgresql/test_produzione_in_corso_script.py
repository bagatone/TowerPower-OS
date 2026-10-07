"""Il riepilogo di sola lettura della produzione in corso gira su PG reale e non scrive."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_planning_in_progress_semine import _seed
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-06_produzione_in_corso.py"


def _module():
    spec = importlib.util.spec_from_file_location("produzione_in_corso", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_totals_per_variety_split_ready_and_not_ready(planning_database):
    engine = planning_database
    _seed(engine, [("SEM-000901", "HVT-0108-A", 3, "2026-08-05", "2026-08-10", 2),
                   ("SEM-000902", "HVT-0208-A", 5, "2026-08-25", "2026-08-30", 0)], harvested_loaded=True)
    url = engine.url
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)
    lines: list[str] = []
    assert _module().run(conn, now=datetime(2026, 8, 15, 6, tzinfo=timezone.utc), out=lines.append) == 0
    text = "\n".join(lines)
    assert "NULLA E' STATO SCRITTO" in text
    total = [l for l in lines if l.startswith("Writer test variety | 8")][0]
    assert total.split(" | ")[:5] == ["Writer test variety", "8", "2", "6", "1"]     # attesi 8, raccolti 2, residui 6, pronti 1
    assert total.endswith("| 0 | 25/08")
    conn.close()
