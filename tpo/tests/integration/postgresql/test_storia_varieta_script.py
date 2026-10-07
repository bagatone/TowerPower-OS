"""La storia di una varieta' (sola lettura) gira su PG reale e non scrive."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_planning_in_progress_semine import _seed
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-06_storia_varieta.py"


def _module():
    spec = importlib.util.spec_from_file_location("storia_varieta", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_history_lists_semine_harvests_movements_and_stock(planning_database):
    engine = planning_database
    _seed(engine, [("SEM-000901", "HVT-0108-A", 3, "2026-08-05", "2026-08-10", 2)], harvested_loaded=True)
    url = engine.url
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)
    lines: list[str] = []
    module = _module()
    assert module.run(conn, ["writer test variety"], out=lines.append) == 0
    text = "\n".join(lines)
    assert "SEM-000901" in text and "RAC-000901" in text and "MOV-000901" in text and "Stock disponibile" in text
    assert "NULLA E' STATO SCRITTO" in text
    assert module.run(conn, ["inesistente"], out=lines.append) == 2
    conn.close()
