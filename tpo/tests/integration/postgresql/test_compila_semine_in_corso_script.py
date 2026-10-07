"""Script di compilazione semine in corso: anteprima senza scritture, blocco senza SET dichiarati, scrittura atomica."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_production_planning_end_to_end import _scalar
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)
from tests.integration.postgresql.test_semina_predictive_authority import _seed

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-06_compila_semine_in_corso.py"


def _module():
    spec = importlib.util.spec_from_file_location("compila_semine_in_corso", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _conn(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def test_preview_and_blocking_and_execution(planning_database):
    engine, module = planning_database, _module()
    _seed(engine, grams="7")
    quartet = "SELECT expected_useful_quantity IS NULL FROM tpo.semine WHERE public_id='SEM-000901'"
    lines = []
    conn = _conn(engine)
    # senza SET dichiarati: bloccato anche con --esegui, nulla scritto
    assert module.run(conn, {}, [], True, out=lines.append) == 2
    assert "SERVE_SET" in "\n".join(lines) and _scalar(engine, quartet)
    # con SET dichiarati, anteprima: nulla scritto
    lines.clear()
    assert module.run(conn, {"SEM-000901": 1}, [], False, out=lines.append) == 0
    assert "ANTEPRIMA" in "\n".join(lines) and _scalar(engine, quartet)
    # esclusa: niente da scrivere
    assert module.run(conn, {}, ["SEM-000901"], True, out=lines.append) == 0 and _scalar(engine, quartet)
    # esecuzione
    lines.clear()
    assert module.run(conn, {"SEM-000901": 1}, [], True, out=lines.append) == 0
    conn.close()
    assert "FATTO" in "\n".join(lines) and not _scalar(engine, quartet)
    assert _scalar(engine, "SELECT expected_useful_quantity FROM tpo.semine WHERE public_id='SEM-000901'") == 1
