"""La lettura di un programma di fornitura (sola lettura) gira su PG reale: query valide e programma inesistente."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-07_programma_fornitura.py"


def _module():
    spec = importlib.util.spec_from_file_location("programma_fornitura", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_queries_are_valid_and_unknown_program_stops(planning_database):
    url = planning_database.url
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)
    module, cur = _module(), conn.cursor()
    for sql in (module.SQL_VERSIONS, module.SQL_LINES):
        cur.execute(sql, (-1,))
        assert cur.fetchall() == []
    cur.execute(module.SQL_ORDERS, ("PF-999999",))
    assert cur.fetchall() == []
    lines: list[str] = []
    assert module.run(conn, "PF-999999", out=lines.append) == 2 and "STOP" in lines[0]
    conn.close()
