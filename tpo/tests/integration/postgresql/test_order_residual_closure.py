"""Real PostgreSQL: chiusura del residuo non piu' dovuto di un ordine parzialmente evaso."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
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


def test_script_solo_chiudibili_lists_the_rest_and_closes_only_the_closable(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _partial(engine)                                                   # ORD-940101: PARZIALMENTE_EVASO, chiudibile
    _delivery_seed(engine, 940102, stock="2", order_quantity="2")      # ORD-940102: APERTO, nessuna consegna
    spec = importlib.util.spec_from_file_location("chiudi_residuo_ordini_b", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    url, lines = engine.url, []
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)
    ids = ["ORD-940101", "ORD-940102"]
    assert module.run(conn, ids, False, out=lines.append) == 2                      # senza l'opzione: tutto rifiutato
    lines.clear()
    assert module.run(conn, ids, False, out=lines.append, solo_chiudibili=True) == 0
    testo = "\n".join(lines)
    assert "NON CHIUDIBILI (1)" in testo and "ORD-940102" in testo and "stato APERTO" in testo and "ANTEPRIMA" in testo
    assert module.run(conn, ids, True, out=lines.append, solo_chiudibili=True, oggi=date(2026, 10, 15)) == 0
    assert module.run(conn, ["ORD-940102"], False, out=lines.append, solo_chiudibili=True) == 2     # nessuno chiudibile
    assert module.run(conn, ["ORD-999999"], False, out=lines.append, solo_chiudibili=True) == 2      # inesistente
    conn.close()
    assert _scalar(engine, "SELECT stato::text FROM tpo.ordini WHERE public_id='ORD-940101'") == "EVASO"
    assert _scalar(engine, "SELECT stato::text FROM tpo.ordini WHERE public_id='ORD-940102'") == "APERTO"
    assert _scalar(engine, "SELECT count(*) FROM tpo.audit_eventi WHERE correlation_id='chiudi-residuo-ordini-2026-10-15' "
                           "AND reason LIKE '%%dichiarato da Matteo il 15/10/2026%%'") >= 1


def _partial_with_unserved_line(engine):
    """ORD-940201: due righe da 2 SET; la prima consegnata per intero, la seconda mai consegnata."""
    _delivery_seed(engine, 940201, stock="2", lines=2, order_quantity="2")
    _delivery_writer(engine).publish(_delivery_command(940201, "2", movement=940201))
    assert _scalar(engine, "SELECT stato::text FROM tpo.ordini WHERE public_id='ORD-940201'") == "PARZIALMENTE_EVASO"


def test_never_delivered_line_is_waived_not_zeroed_and_order_becomes_evaso(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _partial_with_unserved_line(engine)
    before = _snapshot(engine)

    orders, _ = _close(engine, ("ORD-940201",))

    assert [line.never_delivered for line in orders[0].lines] == [False, True]
    assert _scalar(engine, "SELECT stato::text FROM tpo.ordini WHERE public_id='ORD-940201'") == "EVASO"
    righe = _scalar(engine, "SELECT string_agg(quantita::text||'/'||quantita_rinunciata::text, ',' ORDER BY posizione) "
                            "FROM tpo.righe_ordine ro JOIN tpo.ordini o ON o.id=ro.ordine_id "
                            "WHERE o.public_id='ORD-940201'")
    assert righe == "2.000000/0.000000,2.000000/2.000000"      # quantita' ordinata MAI toccata
    assert _snapshot(engine) == before
    audit = _scalar(engine, "SELECT after_data->>'residual_waived' FROM tpo.audit_eventi "
                            "WHERE entity_type='RIGA_ORDINE' AND correlation_id='residuo-test' "
                            "AND entity_public_id='RO-940202'")
    assert audit == "2.000000"


def test_waived_order_is_invisible_to_demand_and_cannot_be_reopened_by_state(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _partial_with_unserved_line(engine)
    _close(engine, ("ORD-940201",))
    # nessuna domanda residua: la lettura del planner considera solo APERTO / PARZIALMENTE_EVASO
    assert _scalar(engine, "SELECT count(*) FROM tpo.ordini WHERE public_id='ORD-940201' "
                           "AND stato IN ('APERTO','PARZIALMENTE_EVASO')") == 0
    # il database rifiuta uno stato incoerente con consegnato + rinunciato
    with pytest.raises(Exception, match="ct_ordini_fulfilment_state"):
        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE tpo.ordini SET stato='PARZIALMENTE_EVASO' WHERE public_id='ORD-940201'")
    # la rinuncia non puo' superare la quantita' ordinata
    with pytest.raises(Exception, match="ck_righe_ordine_quantita_rinunciata_range"):
        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE tpo.righe_ordine SET quantita_rinunciata=quantita+1 "
                                       "WHERE public_id='RO-940202'")


def test_order_with_no_delivered_line_is_not_closable_by_residual(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _delivery_seed(engine, 940301, stock="2", lines=2, order_quantity="2")      # APERTO, nessuna consegna
    with pytest.raises(OrderResidualClosureError, match="PARZIALMENTE_EVASO"):
        _close(engine, ("ORD-940301",))
