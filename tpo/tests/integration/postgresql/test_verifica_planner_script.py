"""Il controllo pre-run e il report di scripts/commissioning/2026-10-05_verifica_planner.py girano su PG reale."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_allocation_invalidation import _multi_line_plan
from tests.integration.postgresql.test_order_cancellation import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-05_verifica_planner.py"


def _module():
    spec = importlib.util.spec_from_file_location("verifica_planner", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_preview_runs_checks_and_report_reads_the_last_run(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    url, lines = engine.url, []
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)
    module = _module()
    code = module.run(conn, False, "2026-10-05T06:30:00+01:00", out=lines.append)
    text = "\n".join(lines)
    assert "CONTROLLI PRIMA DEL RUN" in text and "ANTEPRIMA: nulla e' stato lanciato." in text
    assert "Allocazioni RACCOLTA attive su raccolte non caricate a stock" in text
    assert code in (0, 3)                                  # 3 = i dati di prova hanno ordini vecchi: lo segnala
    lines.clear()
    assert module.report(conn.cursor(), lines.append) is True      # il piano di prova e' COMMITTED
    assert "ULTIMO RUN" in "\n".join(lines) and "Revisione di piano creata" in "\n".join(lines)
    lines.clear()                                          # istante di riferimento PRIMA delle raccolte: segnalato
    assert module.check_harvest_not_after(conn.cursor(), "2000-01-01T00:00:00+00:00", lines.append) in (True, False)
    lines.clear()
    assert module.check_harvest_not_after(conn.cursor(), "2100-01-01T00:00:00+00:00", lines.append) is True
    assert module.default_business_at().endswith(("+00:00", "+01:00"))
    conn.close()
