"""Le query dello script di registrazione semina passata girano su PG reale (find, protocollo, finestra attesa)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_planning_in_progress_semine import _seed
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-06_registra_semina_passata.py"


def _module():
    spec = importlib.util.spec_from_file_location("registra_semina_passata_sql", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_queries_run_against_real_schema(planning_database):
    engine = planning_database
    _seed(engine, [("SEM-000901", "HVT-0108-A", 3, "2026-08-05", "2026-08-10", 0)])
    url = engine.url
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)
    cur = conn.cursor()
    module = _module()
    found = module.find(cur, "Writer test variety", date(2026, 7, 25))
    assert found and found[0][0] == "SEM-000901" and found[0][4] is True
    assert module.find(cur, "Writer test variety", date(2000, 1, 1)) == []
    cur.execute("SELECT public_id FROM tpo.protocollo_versioni LIMIT 1")
    pv = cur.fetchone()[0]
    started = datetime(2026, 9, 29, 9, 0, tzinfo=timezone(timedelta(hours=1)))
    window = module.expected_window(cur, pv, 1, started, 5)
    assert window is None or window.window_end - window.window_start == timedelta(days=5)
    conn.close()
