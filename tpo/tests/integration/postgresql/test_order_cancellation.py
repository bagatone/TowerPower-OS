"""Real PostgreSQL: chiusura (ANNULLATO) di ordini storici scaduti senza consegne.

Scenario reale (5/10/2026): ordini ricorrenti dello scheduler di agosto/settembre
mai evasi a sistema; ordini futuri e ordini con consegne NON vanno toccati.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.tpo_core.infrastructure.postgresql.order_cancellation import (
    OrderCancellationError, cancel, eligible, preview,
)
from src.tpo_core.infrastructure.postgresql.pianificazione_semina_lettura import (
    PostgreSQLPianificazioneSeminaLetturaReader,
)
from src.tpo_core.application.pianificazione_semina_lettura.models import RichiediElencoDaSeminare
from src.tpo_core.infrastructure.postgresql.production_planning_input import (
    PostgreSQLProductionPlanningInputAdapter,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    _command as _delivery_command, _seed as _delivery_seed, _writer as _delivery_writer,
    writer_postgresql_cluster_engine, writer_postgresql_engine,
)
from tests.integration.postgresql.test_allocation_invalidation import _multi_line_plan
from tests.integration.postgresql.test_production_planning_end_to_end import _command, _scalar
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

BEFORE = date(2026, 8, 14)   # soglia esclusiva: chiude RO-000002 (12/8) e RO-000003 (13/8)
REASON = "ordine storico scaduto, chiuso da Matteo; nessuna consegna registrata"


def _run(engine, fn, **kwargs):
    with engine.begin() as connection:
        cursor = connection.connection.cursor()
        try:
            return fn(cursor, **kwargs)
        finally:
            cursor.close()


def _cancel(engine, ids, before=BEFORE):
    return _run(engine, cancel, order_public_ids=ids, before=before, actor="matteo",
                reason=REASON, correlation_id="chiudi-test", provenance="test-e2e")


def _state(engine):
    with engine.connect() as c:
        return {
            "orders": c.exec_driver_sql("SELECT public_id,stato::text,version FROM tpo.ordini ORDER BY 1").all(),
            "alloc": c.exec_driver_sql("SELECT public_id,state,version FROM tpo.allocazioni ORDER BY 1").all(),
            "stock": c.exec_driver_sql("SELECT disponibile,version FROM tpo.stock").all(),
            "lines": c.exec_driver_sql("SELECT public_id,version FROM tpo.righe_ordine ORDER BY 1").all(),
            "plan": c.exec_driver_sql("SELECT public_id,stato FROM tpo.righe_piano_semina ORDER BY 1").all(),
            "movements": c.exec_driver_sql("SELECT count(*) FROM tpo.movimenti_magazzino").all(),
        }


def test_cancels_only_expired_orders_and_releases_their_allocations(planning_database):
    engine = planning_database
    _multi_line_plan(engine)        # ORD-000001 (15/8), 2 (12/8), 3 (13/8), 4 (14/8)
    before = _state(engine)

    orders, released = _cancel(engine, ("ORD-000002", "ORD-000003"))

    assert [o.public_id for o in orders] == ["ORD-000002", "ORD-000003"]
    after = _state(engine)
    assert dict((r[0], r[1]) for r in after["orders"]) == {
        "ORD-000001": "APERTO", "ORD-000002": "ANNULLATO", "ORD-000003": "ANNULLATO", "ORD-000004": "APERTO"}
    assert {r.public_id for r in released} == {"ALL-000001", "ALL-000002"}
    assert dict((r[0], r[1]) for r in after["alloc"]) == {
        "ALL-000001": "RILASCIATA", "ALL-000002": "RILASCIATA",
        "ALL-000003": "ATTIVA", "ALL-000004": "ATTIVA", "ALL-000005": "ATTIVA"}
    # nient'altro cambia: stock, righe d'ordine, righe di piano, movimenti
    for key in ("stock", "lines", "plan", "movements"):
        assert after[key] == before[key]
    assert _scalar(engine, "SELECT count(*) FROM tpo.transizioni_allocazione "
                           "WHERE transition_type='RILASCIATA'") == 2
    assert _scalar(engine, "SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='ORDINE' "
                           "AND operation='STATE_TRANSITION' AND actor='matteo'") == 2
    assert _scalar(engine, "SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='ALLOCAZIONE' "
                           "AND actor='matteo'") == 2


def test_closed_orders_leave_demand_and_da_seminare_but_planning_still_loads(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    reader = PostgreSQLPianificazioneSeminaLetturaReader(_Factory(engine))
    assert {r.riga_id.value for r in reader.elenco(RichiediElencoDaSeminare()).righe}   # c'e' roba da seminare
    _cancel(engine, ("ORD-000001", "ORD-000002", "ORD-000003", "ORD-000004"), before=date(2026, 9, 1))

    assert reader.elenco(RichiediElencoDaSeminare()).righe == ()
    loaded = PostgreSQLProductionPlanningInputAdapter(_Factory(engine)).load(_command("dopo-chiusura"))
    assert loaded.snapshot.demands == ()
    assert not [a for a in loaded.snapshot.allocations if a.state == "ATTIVA"]


def test_rejects_future_unknown_and_already_closed_orders_atomically(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    before = _state(engine)
    with pytest.raises(OrderCancellationError, match="non anteriore"):
        _cancel(engine, ("ORD-000002", "ORD-000004"), before=date(2026, 8, 14))   # ORD-000004 = 14/8
    with pytest.raises(OrderCancellationError, match="inesistenti"):
        _cancel(engine, ("ORD-000002", "ORD-999999"))
    assert _state(engine) == before
    _cancel(engine, ("ORD-000002",))
    with pytest.raises(OrderCancellationError, match="stato ANNULLATO"):
        _cancel(engine, ("ORD-000002",))


def test_eligible_lists_only_expired_open_orders_without_deliveries(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    ok, skipped = _run(engine, eligible, before=date(2026, 8, 14))
    assert [o.public_id for o in ok] == ["ORD-000002", "ORD-000003"] and skipped == ()
    found, allocations = _run(engine, preview, order_public_ids=("ORD-000002",), before=BEFORE)
    assert len(found) == 1 and [a.public_id for a in allocations] == ["ALL-000001"]
    assert _scalar(engine, "SELECT count(*) FROM tpo.transizioni_allocazione") == 0   # anteprima: nulla scritto


def test_order_with_registered_delivery_cannot_be_cancelled(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _delivery_seed(engine, 940101, stock="2", order_quantity="2")
    _delivery_writer(engine).publish(_delivery_command(940101, "1", movement=940101))
    assert _scalar(engine, "SELECT stato::text FROM tpo.ordini WHERE public_id='ORD-940101'") == "PARZIALMENTE_EVASO"
    with pytest.raises(OrderCancellationError, match="PARZIALMENTE_EVASO"):
        _cancel(engine, ("ORD-940101",), before=date(2100, 1, 1))
    assert _scalar(engine, "SELECT stato::text FROM tpo.ordini WHERE public_id='ORD-940101'") == "PARZIALMENTE_EVASO"


def test_next_planning_run_commits_with_only_the_remaining_open_orders(planning_database):
    from tests.integration.postgresql.test_production_planning_end_to_end import _service
    engine = planning_database
    _multi_line_plan(engine)
    _cancel(engine, ("ORD-000002", "ORD-000003"))

    assert _service(engine).execute(_command("dopo-chiusura-run")).run_state == "COMMITTED"

    with engine.connect() as c:
        rows = c.exec_driver_sql(
            "SELECT ro.public_id FROM tpo.righe_piano_semina l JOIN tpo.righe_ordine ro ON ro.id=l.riga_ordine_id "
            "JOIN tpo.piano_produzione_revisioni r ON r.id=l.piano_revisione_id "
            "WHERE r.id=(SELECT max(id) FROM tpo.piano_produzione_revisioni) ORDER BY 1").all()
    assert [r[0] for r in rows] == ["RO-000001", "RO-000004"]


def _plan_with_unloaded_harvest(engine) -> None:
    """Stock 0, una raccolta da 2 SET NON caricata a magazzino: il planner la alloca (RACCOLTA)."""
    from tests.integration.postgresql.test_production_planning_end_to_end import _seed_identity, _service
    _seed_identity(engine)
    with engine.begin() as c:
        c.exec_driver_sql("""
        INSERT INTO tpo.ordini (public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,created_by,version)
        SELECT 'ORD-00000'||n,(SELECT id FROM tpo.clienti LIMIT 1),DATE '2026-08-01',(DATE '2026-08-10' + n),
               'APERTO','MANUALE','test',0 FROM generate_series(2,3) n;
        INSERT INTO tpo.righe_ordine (public_id,ordine_id,posizione,varieta_id,quantita,unita_misura,version)
        SELECT 'RO-00000'||n,o.id,1,(SELECT id FROM tpo.varieta LIMIT 1),1,'SET',0
        FROM generate_series(2,3) n JOIN tpo.ordini o ON o.public_id='ORD-00000'||n;
        UPDATE tpo.stock SET disponibile=0;
        """)
        c.exec_driver_sql("SET LOCAL session_replication_role = replica")
        c.exec_driver_sql("""
          INSERT INTO tpo.semine
            (public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,protocollo_versione_id,stato,
             quantita_seme,unita_misura,data_avvio,causa_origine,cultivar_snapshot,uso_produttivo_snapshot,
             lotto_seme_snapshot,protocollo_snapshot,created_by,codice_tracciabilita)
          SELECT 'SEM-000901',id,1,1,1,1,'PRONTA_ALLA_RACCOLTA',10,'GRAM',TIMESTAMPTZ '2026-08-01 06:00+00',
                 'PIANO_PRODUZIONE','x','x','x','x','test','HVT-0108-A' FROM tpo.varieta LIMIT 1;
          INSERT INTO tpo.raccolte (public_id,semina_id,data_raccolta,quantita,unita_misura,created_by)
          SELECT 'RAC-000901',id,TIMESTAMPTZ '2026-08-10 06:00+00',2,'SET','test'
          FROM tpo.semine WHERE public_id='SEM-000901';
        """)
    assert _service(engine).execute(_command("e2e-harvest")).run_state == "COMMITTED"
    assert _scalar(engine, "SELECT count(*) FROM tpo.allocazioni WHERE allocation_type='RACCOLTA' "
                           "AND state='ATTIVA'") >= 1


def test_harvest_allocation_on_unloaded_harvest_blocks_closure_until_loaded(planning_database):
    engine = planning_database
    _plan_with_unloaded_harvest(engine)
    before = _state(engine)
    with pytest.raises(OrderCancellationError, match="RACCOLTA"):
        _cancel(engine, ("ORD-000002", "ORD-000003"))
    assert _state(engine) == before            # nulla scritto

    with engine.begin() as c:                  # la raccolta viene caricata a stock (e venduta altrove)
        c.exec_driver_sql("""
          INSERT INTO tpo.movimenti_magazzino
            (public_id,varieta_id,unita_misura,tipo,direzione,quantita,data_movimento,motivo,origine_tipo,
             raccolta_id,created_at,created_by)
          SELECT 'MOV-000901',r.varieta_id,'SET','CARICO','POSITIVO',2,TIMESTAMPTZ '2026-08-10 07:00+00',
                 'carico da raccolta','RACCOLTA',rc.id,TIMESTAMPTZ '2026-08-10 07:00+00','test'
          FROM tpo.raccolte rc JOIN tpo.semine s ON s.id=rc.semina_id
          JOIN tpo.righe_ordine r ON r.public_id='RO-000001' WHERE rc.public_id='RAC-000901'
        """)
    _, released = _cancel(engine, ("ORD-000002", "ORD-000003"))
    assert any(a.allocation_type == "RACCOLTA" for a in released)
    assert _scalar(engine, "SELECT count(*) FROM tpo.allocazioni a JOIN tpo.righe_piano_semina l "
                           "ON l.id=a.riga_piano_semina_id JOIN tpo.righe_ordine ro ON ro.id=l.riga_ordine_id "
                           "JOIN tpo.ordini o ON o.id=ro.ordine_id WHERE a.state='ATTIVA' "
                           "AND o.public_id IN ('ORD-000002','ORD-000003')") == 0
