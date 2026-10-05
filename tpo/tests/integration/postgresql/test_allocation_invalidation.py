"""Real PostgreSQL: invalidazione governata di allocazioni STOCK obsolete.

Scenario reale (5/10/2026): 3 allocazioni STOCK su 3 righe d'ordine di vecchi
ordini, merce venduta fuori sistema (stock 0), piano con altre righe da
produrre. Si chiudono SOLO le 3 allocazioni; nient'altro cambia.
"""

from __future__ import annotations

import pytest

from src.tpo_core.infrastructure.postgresql.allocation_invalidation import (
    AllocationInvalidationError, invalidate, preview,
)
from src.tpo_core.infrastructure.postgresql.production_planning_input import (
    PostgreSQLProductionPlanningInputAdapter,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.integration.postgresql.test_production_planning_end_to_end import (
    _command, _scalar, _seed_identity, _service,
)
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

STOCK = ("ALL-000001", "ALL-000002", "ALL-000003")


def _multi_line_plan(engine) -> None:
    """Stock 3 SET: RO-000002/3/4 coperte da STOCK, RO-000001 e il resto di RO-000004
    da produrre (allocazioni DOMANDA)."""
    _seed_identity(engine)
    with engine.begin() as c:
        c.exec_driver_sql("""
        INSERT INTO tpo.ordini (public_id,cliente_id,data_ordine,data_consegna_prevista,
                                stato,tipo_creazione,created_by,version)
        SELECT 'ORD-00000'||n,(SELECT id FROM tpo.clienti LIMIT 1),DATE '2026-08-01',
               (DATE '2026-08-10' + n),'APERTO','MANUALE','test',0
        FROM generate_series(2,4) n;
        INSERT INTO tpo.righe_ordine (public_id,ordine_id,posizione,varieta_id,quantita,
                                      unita_misura,version)
        SELECT 'RO-00000'||n,o.id,1,(SELECT id FROM tpo.varieta LIMIT 1),
               CASE WHEN n=4 THEN 2 ELSE 1 END,'SET',0
        FROM generate_series(2,4) n JOIN tpo.ordini o ON o.public_id='ORD-00000'||n;
        UPDATE tpo.stock SET disponibile=3;
        """)
    assert _service(engine).execute(_command("e2e-multi")).run_state == "COMMITTED"
    assert _scalar(engine, "SELECT count(*) FROM tpo.allocazioni WHERE allocation_type='STOCK' "
                           "AND state='ATTIVA'") == 3


def _sold_outside_the_system(engine) -> None:
    with engine.begin() as c:
        c.exec_driver_sql("UPDATE tpo.stock SET disponibile=0")


def _run(engine, ids, fn=invalidate, **extra):
    with engine.begin() as connection:
        cursor = connection.connection.cursor()
        try:
            return fn(cursor, allocation_public_ids=ids, **extra)
        finally:
            cursor.close()


def _invalidate(engine, ids=STOCK):
    return _run(engine, ids, actor="matteo", reason="stock venduto, vendita non registrata",
                correlation_id="inv-test", provenance="test-e2e")


def _snapshot(engine):
    with engine.connect() as c:
        return {
            "orders": c.exec_driver_sql("SELECT public_id,stato,version FROM tpo.ordini ORDER BY 1").all(),
            "lines": c.exec_driver_sql("SELECT public_id,version FROM tpo.righe_ordine ORDER BY 1").all(),
            "stock": c.exec_driver_sql("SELECT varieta_id,disponibile,version FROM tpo.stock").all(),
            "revisions": c.exec_driver_sql("SELECT public_id FROM tpo.piano_produzione_revisioni").all(),
            "plan_lines": c.exec_driver_sql("SELECT public_id,stato,version FROM tpo.righe_piano_semina ORDER BY 1").all(),
            "domanda": c.exec_driver_sql(
                "SELECT public_id,state,version FROM tpo.allocazioni WHERE allocation_type='DOMANDA' ORDER BY 1").all(),
            "movements": c.exec_driver_sql("SELECT count(*) FROM tpo.movimenti_magazzino").all(),
        }


def test_stale_stock_allocations_block_planning_and_invalidation_clears_only_them(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    _sold_outside_the_system(engine)
    loader = PostgreSQLProductionPlanningInputAdapter(_Factory(engine))
    with pytest.raises(Exception) as blocked:
        loader.load(_command("e2e-blocked"))
    assert blocked.value.code == "RESOURCE_OVERALLOCATED"
    before = _snapshot(engine)

    done = _invalidate(engine)

    assert [item.public_id for item in done] == list(STOCK)
    with engine.connect() as c:
        assert c.exec_driver_sql(
            "SELECT public_id,state,version FROM tpo.allocazioni "
            "WHERE allocation_type='STOCK' ORDER BY 1").all() == [
            ("ALL-000001", "INVALIDA", 1), ("ALL-000002", "INVALIDA", 1), ("ALL-000003", "INVALIDA", 1)]
        assert c.exec_driver_sql(
            "SELECT t.transition_type,t.quantity,t.expected_allocation_version,t.created_by "
            "FROM tpo.transizioni_allocazione t ORDER BY t.id").all() == [
            ("INVALIDA", 1, 0, "matteo")] * 3
        assert c.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='ALLOCAZIONE' "
            "AND operation='STATE_TRANSITION' AND actor='matteo'").scalar_one() == 3
    assert _snapshot(engine) == before          # nient'altro e' cambiato
    loaded = loader.load(_command("e2e-after"))  # il blocco reale e' sparito
    assert not [a for a in loaded.snapshot.allocations
                if a.allocation_type == "STOCK" and a.state == "ATTIVA"]


def test_non_stale_allocation_is_refused_and_nothing_changes(planning_database):
    engine = planning_database
    _multi_line_plan(engine)                       # stock 3 copre 3 allocazioni
    before = _snapshot(engine)
    with pytest.raises(AllocationInvalidationError, match="non e' obsoleta"):
        _invalidate(engine, ("ALL-000001",))
    assert _snapshot(engine) == before
    assert _scalar(engine, "SELECT count(*) FROM tpo.transizioni_allocazione") == 0


def test_never_invalidates_more_than_the_real_shortfall(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    with engine.begin() as c:
        c.exec_driver_sql("UPDATE tpo.stock SET disponibile=2")   # scoperto reale = 1
    with pytest.raises(AllocationInvalidationError, match="supera lo scoperto"):
        _invalidate(engine, ("ALL-000001", "ALL-000002"))
    assert _scalar(engine, "SELECT count(*) FROM tpo.transizioni_allocazione") == 0
    _invalidate(engine, ("ALL-000001",))                           # esattamente lo scoperto
    assert _scalar(engine, "SELECT count(*) FROM tpo.transizioni_allocazione") == 1


def test_is_all_or_nothing_and_not_repeatable(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    _sold_outside_the_system(engine)
    with pytest.raises(AllocationInvalidationError, match="inesistenti"):
        _invalidate(engine, ("ALL-000001", "ALL-999999"))
    assert _scalar(engine, "SELECT count(*) FROM tpo.transizioni_allocazione") == 0
    _invalidate(engine)
    with pytest.raises(AllocationInvalidationError, match="non e' ATTIVA"):
        _invalidate(engine, ("ALL-000001",))
    assert _scalar(engine, "SELECT count(*) FROM tpo.transizioni_allocazione") == 3


def test_domanda_allocation_is_never_accepted(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    _sold_outside_the_system(engine)
    with pytest.raises(AllocationInvalidationError, match="non e' di tipo STOCK"):
        _invalidate(engine, ("ALL-000004",))


def test_preview_is_read_only(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    _sold_outside_the_system(engine)
    before = _snapshot(engine)
    rows = _run(engine, STOCK, fn=preview)
    assert [r.public_id for r in rows] == list(STOCK) and all(r.stale for r in rows)
    assert _snapshot(engine) == before
    assert _scalar(engine, "SELECT count(*) FROM tpo.transizioni_allocazione") == 0
