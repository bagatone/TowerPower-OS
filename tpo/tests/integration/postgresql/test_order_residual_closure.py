"""Real PostgreSQL: chiusura del residuo non piu' dovuto di un ordine parzialmente evaso."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg
import pytest

from src.tpo_core.infrastructure.postgresql.order_residual_closure import (
    OrderResidualClosureError, close_residual, preview,
)
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    _command as _delivery_command, _seed as _delivery_seed, _writer as _delivery_writer,
    writer_postgresql_cluster_engine, writer_postgresql_engine,
)
from tests.integration.postgresql.test_production_planning_end_to_end import _scalar
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

REASON = "residuo non piu' dovuto, dichiarato da Matteo"
SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-05_chiudi_residuo_ordini.py"


def _partial(engine):
    _delivery_seed(engine, 940101, stock="2", order_quantity="2")
    _delivery_writer(engine).publish(_delivery_command(940101, "1", movement=940101))
    assert _scalar(engine, "SELECT stato::text FROM tpo.ordini WHERE public_id='ORD-940101'") == "PARZIALMENTE_EVASO"


def _close(engine, ids=("ORD-940101",)):
    with engine.begin() as connection:
        cursor = connection.connection.cursor()
        try:
            return close_residual(cursor, order_public_ids=ids, actor="matteo", reason=REASON,
                                  correlation_id="residuo-test", provenance="test-e2e")
        finally:
            cursor.close()


def _snapshot(engine):
    with engine.connect() as c:
        return {t: c.exec_driver_sql(q).all() for t, q in {
            "consegne": "SELECT public_id,stato::text FROM tpo.consegne ORDER BY 1",
            "righe_consegna": "SELECT riga_ordine_id,quantita FROM tpo.righe_consegna ORDER BY 1",
            "stock": "SELECT disponibile,version FROM tpo.stock",
            "movimenti": "SELECT count(*) FROM tpo.movimenti_magazzino",
        }.items()}


def test_closes_residual_keeps_deliveries_and_audits_original_quantity(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _partial(engine)
    before = _snapshot(engine)

    orders, _ = _close(engine)

    assert orders[0].lines[0].ordered == 2 and orders[0].lines[0].delivered == 1
    assert _scalar(engine, "SELECT stato::text FROM tpo.ordini WHERE public_id='ORD-940101'") == "EVASO"
    assert _scalar(engine, "SELECT quantita FROM tpo.righe_ordine ro JOIN tpo.ordini o ON o.id=ro.ordine_id "
                           "WHERE o.public_id='ORD-940101'") == 1
    assert _snapshot(engine) == before                     # consegne, stock, movimenti intatti
    original = _scalar(engine, "SELECT before_data->>'ordered' FROM tpo.audit_eventi "
                               "WHERE entity_type='RIGA_ORDINE' AND correlation_id='residuo-test'")
    assert original == "2.000000"


def test_rejects_orders_without_deliveries_or_already_closed_and_writes_nothing(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _partial(engine)
    _close(engine)
    with pytest.raises(OrderResidualClosureError, match="PARZIALMENTE_EVASO"):
        _close(engine)                                     # gia' EVASO: niente doppia chiusura
    with pytest.raises(OrderResidualClosureError, match="inesistenti"):
        _close(engine, ("ORD-999999",))
    assert _scalar(engine, "SELECT count(*) FROM tpo.audit_eventi WHERE correlation_id='residuo-test' "
                           "AND entity_type='ORDINE'") == 1


def test_script_preview_writes_nothing_then_execute(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _partial(engine)
    spec = importlib.util.spec_from_file_location("chiudi_residuo_ordini", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    url, lines = engine.url, []
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)
    assert module.run(conn, ["ORD-940101"], False, out=lines.append) == 0
    assert "ANTEPRIMA" in "\n".join(lines)
    assert _scalar(engine, "SELECT stato::text FROM tpo.ordini WHERE public_id='ORD-940101'") == "PARZIALMENTE_EVASO"
    assert module.run(conn, ["ORD-940101"], True, out=lines.append) == 0
    conn.close()
    assert _scalar(engine, "SELECT stato::text FROM tpo.ordini WHERE public_id='ORD-940101'") == "EVASO"
