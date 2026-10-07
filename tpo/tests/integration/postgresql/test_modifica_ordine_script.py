"""Modifica di UN ordine aperto (quantita' di una riga, data) sul PostgreSQL reale di prova."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg

from tests.integration.postgresql.test_allocation_invalidation import _multi_line_plan, _scalar
from tests.integration.postgresql.test_order_cancellation import _state
from tests.integration.postgresql.test_order_cancellation import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-07_modifica_ordine.py"


def _module():
    spec = importlib.util.spec_from_file_location("modifica_ordine", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def _active(engine, order):
    return _scalar(engine, "SELECT count(*) FROM tpo.allocazioni a JOIN tpo.righe_piano_semina rps ON "
                           "rps.id=a.riga_piano_semina_id JOIN tpo.righe_ordine ro ON ro.id=rps.riga_ordine_id "
                           f"JOIN tpo.ordini o ON o.id=ro.ordine_id WHERE o.public_id='{order}' AND a.state='ATTIVA'")


def test_quantity_preview_writes_nothing_then_execute_keeps_original_in_audit(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    module, lines, before = _module(), [], _state(engine)
    assert _active(engine, "ORD-000004") > 0 and _active(engine, "ORD-000003") > 0

    conn = _connect(engine)
    assert module.run_quantita(conn, "ORD-000004", "RO-000004", Decimal("1"), "cliente ha ridotto", False,
                               out=lines.append) == 0
    conn.close()
    assert "2 SET -> 1 SET" in "\n".join(lines) and "ANTEPRIMA: nulla e' stato scritto" in "\n".join(lines)
    assert _state(engine) == before

    conn = _connect(engine)
    assert module.run_quantita(conn, "ORD-000004", "RO-000004", Decimal("1"), "cliente ha ridotto", True,
                               out=lines.append) == 0
    conn.close()
    assert _scalar(engine, "SELECT quantita FROM tpo.righe_ordine WHERE public_id='RO-000004'") == 1
    assert _scalar(engine, "SELECT stato::text FROM tpo.ordini WHERE public_id='ORD-000004'") == "APERTO"
    assert _active(engine, "ORD-000004") == 0 and _active(engine, "ORD-000003") > 0   # solo quell'ordine
    assert _scalar(engine, "SELECT before_data->>'ordered' FROM tpo.audit_eventi WHERE entity_type='RIGA_ORDINE' "
                           "AND entity_public_id='RO-000004'") == "2.000000"
    assert _scalar(engine, "SELECT after_data->>'amended_from' FROM tpo.audit_eventi WHERE entity_type='RIGA_ORDINE' "
                           "AND entity_public_id='RO-000004'") == "2.000000"
    assert _scalar(engine, "SELECT disponibile FROM tpo.stock") == 3                    # stock intatto


def test_line_selected_by_variety_name_ignoring_case_and_accents(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    name = _scalar(engine, "SELECT denominazione FROM tpo.varieta LIMIT 1")
    conn, lines = _connect(engine), []
    assert _module().run_quantita(conn, "ORD-000003", name.upper(), Decimal("3"), "x", True, out=lines.append) == 0
    conn.close()
    assert _scalar(engine, "SELECT quantita FROM tpo.righe_ordine WHERE public_id='RO-000003'") == 3


def test_date_change_releases_allocations_and_audits_original_date(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    module, lines = _module(), []
    conn = _connect(engine)
    assert module.run_data(conn, "ORD-000002", date(2026, 8, 20), "cliente chiede sabato", True,
                           out=lines.append) == 0
    conn.close()
    assert _scalar(engine, "SELECT data_consegna_prevista::text FROM tpo.ordini WHERE public_id='ORD-000002'") == "2026-08-20"
    assert _active(engine, "ORD-000002") == 0 and _active(engine, "ORD-000003") > 0
    assert _scalar(engine, "SELECT after_data->>'amended_from' FROM tpo.audit_eventi WHERE entity_type='ORDINE' "
                           "AND entity_public_id='ORD-000002'") == "2026-08-12"


def test_refusals_write_nothing(planning_database):
    engine = planning_database
    _multi_line_plan(engine)
    module, lines = _module(), []
    state = _state(engine)
    for call in (
        lambda c: module.run_quantita(c, "ORD-000004", "RO-000004", Decimal("2"), "x", True, out=lines.append),   # uguale
        lambda c: module.run_quantita(c, "ORD-000004", "RO-000004", Decimal("0"), "x", True, out=lines.append),   # zero
        lambda c: module.run_quantita(c, "ORD-000004", "Inesistente", Decimal("1"), "x", True, out=lines.append),
        lambda c: module.run_quantita(c, "ORD-999999", "RO-000004", Decimal("1"), "x", True, out=lines.append),
        lambda c: module.run_data(c, "ORD-000002", date(2026, 7, 1), "x", True, out=lines.append),                # prima dell'ordine
        lambda c: module.run_data(c, "ORD-000002", date(2026, 8, 12), "x", True, out=lines.append),               # uguale
    ):
        conn = _connect(engine)
        assert call(conn) == 2
        conn.close()
    assert "RIFIUTATO" in "\n".join(lines) and _state(engine) == state

    conn = _connect(engine)                          # annullato: non si modifica piu'
    assert module.run_annulla(conn, ["ORD-000004"], "errato", True, out=lines.append) == 0
    conn.close()
    after = _state(engine)
    conn = _connect(engine)
    assert module.run_quantita(conn, "ORD-000004", "RO-000004", Decimal("1"), "x", True, out=lines.append) == 2
    conn.close()
    assert _state(engine) == after
