"""Il piano ipotetico (sola lettura) usa il planner vero, vede le semine in corso e non scrive nulla."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_planning_in_progress_semine import _seed
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-06_piano_ipotetico.py"
BUSINESS_AT = "2026-08-15T06:00:00+01:00"


class _Factory:
    def __init__(self, engine) -> None:
        self.url = engine.url

    def connect(self):
        return psycopg.connect(host=self.url.host, port=self.url.port, dbname=self.url.database,
                               user=self.url.username, connect_timeout=5)


def _module():
    spec = importlib.util.spec_from_file_location("piano_ipotetico", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _counts(engine) -> tuple:
    with engine.connect() as c:
        return tuple(c.exec_driver_sql(f"SELECT count(*) FROM tpo.{t}").scalar_one() for t in (
            "production_planning_runs", "allocazioni", "piano_produzione_revisioni", "righe_piano_semina",
            "audit_eventi", "semine", "id_sequences"))


def test_hypothetical_plan_sees_in_progress_semine_and_writes_nothing(planning_database):
    engine = planning_database
    _seed(engine, [("SEM-000901", "HVT-0108-A", 1, "2026-08-05", "2026-08-10", 0)])
    module, factory = _module(), _Factory(engine)
    before = _counts(engine)
    with engine.connect() as c:
        seq_before = c.exec_driver_sql("SELECT sum(next_value) FROM tpo.id_sequences").scalar_one()

    lines: list[str] = []
    assert module.run(factory, BUSINESS_AT, out=lines.append) == 0
    text = "\n".join(lines)
    assert "NULLA E' STATO SCRITTO" in text and "RIEPILOGO PER VARIETA'" in text
    plan, snapshot = module.hypothetical_plan(factory, BUSINESS_AT)
    with_semina = sum(l.authorized_productive_quantity.value for l in plan.planning_lines)
    covered = sum(l.in_progress_coverage.value for l in plan.planning_lines)
    assert covered == 1                                         # la semina in corso copre 1 SET

    assert _counts(engine) == before                            # nessuna scrittura
    with engine.connect() as c:
        assert c.exec_driver_sql("SELECT sum(next_value) FROM tpo.id_sequences").scalar_one() == seq_before

    with engine.begin() as c:                                   # stessa domanda, semina non compilata
        c.exec_driver_sql("UPDATE tpo.semine SET expected_useful_quantity=NULL, expected_useful_uom=NULL,"
                          "harvest_window_start=NULL, harvest_window_end=NULL")
    plan2, _ = module.hypothetical_plan(factory, BUSINESS_AT)
    without_semina = sum(l.authorized_productive_quantity.value for l in plan2.planning_lines)
    assert without_semina == with_semina + 1                    # senza semina in corso va riseminato 1 SET in piu'


def test_old_allocations_do_not_hold_goods_in_the_hypothetical_plan(planning_database):
    from tests.integration.postgresql.test_allocation_invalidation import _multi_line_plan
    engine = planning_database
    _multi_line_plan(engine)                                    # piano committato: stock 3 SET allocato a 3 righe
    module, factory = _module(), _Factory(engine)
    before = _counts(engine)
    plan, snapshot = module.hypothetical_plan(factory, BUSINESS_AT)
    assert sum(l.stock_coverage.value for l in plan.planning_lines) == 3     # stock visto per intero, non "gia' preso"
    assert snapshot.allocations == ()
    assert _counts(engine) == before


def test_planner_refusal_is_reported_not_raised(planning_database):
    engine = planning_database
    with engine.begin() as c:                                   # nessun ordine aperto: il planner rifiuta
        c.exec_driver_sql("SET LOCAL session_replication_role = replica")
        c.exec_driver_sql("UPDATE tpo.ordini SET stato='ANNULLATO'")
    lines: list[str] = []
    code = _module().run(_Factory(engine), BUSINESS_AT, out=lines.append)
    assert code == 2 and "STOP" in "\n".join(lines)
