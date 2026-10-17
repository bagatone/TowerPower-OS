"""Revisione governata di un protocollo agronomico (nuova versione N+1) sul PostgreSQL reale di prova."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import psycopg
import pytest

from src.tpo_core.infrastructure.postgresql.protocol_revision import (
    ProtocolRevisionError, current_version, prepare,
)
from tests.integration.postgresql.test_raccolta import harvest_environment, scalar  # noqa: F401
from tests.integration.postgresql.test_raccolta import environment  # noqa: F401
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql  # noqa: F401

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-07_revisiona_protocollo.py"
TODAY = date(2026, 10, 7)


def _module():
    spec = importlib.util.spec_from_file_location("revisiona_protocollo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def _variety(engine) -> str:
    return scalar(engine, "SELECT denominazione FROM tpo.varieta ORDER BY id LIMIT 1")


def _snapshot(engine):
    with engine.connect() as connection:
        return (
            connection.exec_driver_sql(
                "SELECT public_id,numero_versione,valida_dal,valida_al,germinazione_giorni,crescita_luce_giorni "
                "FROM tpo.protocollo_versioni ORDER BY id").all(),
            connection.exec_driver_sql("SELECT count(*) FROM tpo.audit_eventi").scalar_one(),
        )


def test_preview_writes_nothing_then_execute_creates_next_version(harvest_environment):
    engine, _writer = harvest_environment
    module, lines, name = _module(), [], _variety(engine)
    old_germ = scalar(engine, "SELECT germinazione_giorni FROM tpo.protocollo_versioni WHERE public_id='PV-000001'")
    before = _snapshot(engine)
    changes = {"germination_days": old_germ + 1, "light_growth_days": 3}

    conn = _connect(engine)
    assert module.run(conn, name, changes, None, "tempi reali di campo", None, False, today=TODAY,
                      out=lines.append) == 0
    conn.close()
    text = "\n".join(lines)
    assert "ANTEPRIMA: nulla e' stato scritto" in text and "PV-000001" in text and "PV-000002" in text
    assert "SEM-000001" in text                                   # semina aperta resta sulla vecchia
    assert _snapshot(engine) == before

    conn = _connect(engine)
    assert module.run(conn, name, changes, None, "tempi reali di campo", "osservazione in campo", True,
                      today=TODAY, out=lines.append) == 0
    conn.close()

    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT public_id,numero_versione,valida_dal,valida_al,stato_approvazione,germinazione_giorni,"
            "crescita_luce_giorni,grammi_seme_per_set,versione_precedente_id,evidenze,motivazione,"
            "ciclo_produttivo_nominale_giorni FROM tpo.protocollo_versioni ORDER BY id").all()
        old_id = connection.exec_driver_sql("SELECT id FROM tpo.protocollo_versioni WHERE public_id='PV-000001'").scalar_one()
    old, new = rows
    assert old[3] == TODAY and old[4] == "APPROVATA"              # chiusa, non cancellata
    assert new[0] == "PV-000002" and new[1] == old[1] + 1 and new[2] == TODAY and new[3] is None
    assert new[5] == old_germ + 1 and new[6] == 3 and new[7] == old[7]       # campi non indicati ereditati
    assert new[8] == old_id and new[9] == "osservazione in campo" and new[10] == "tempi reali di campo"
    assert new[11] == old_germ + 1 + 3
    assert scalar(engine, "SELECT protocollo_versione_id FROM tpo.semine WHERE public_id='SEM-000001'") == old_id
    assert scalar(engine, "SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='PROTOCOLLO_VERSIONE' "
                          "AND provenance='commissioning:2026-10-07_revisiona_protocollo'") == 2
    assert scalar(engine, "SELECT after_data->'changes'->'light_growth_days'->>'to' FROM tpo.audit_eventi "
                          "WHERE entity_public_id='PV-000002'") == "3"
    with engine.connect() as connection:
        cursor = connection.connection.cursor()
        assert current_version(cursor, name)["public_id"] == "PV-000002"   # esattamente una corrente


def test_second_run_with_same_values_is_refused_as_no_difference(harvest_environment):
    engine, _writer = harvest_environment
    module, lines, name = _module(), [], _variety(engine)
    light = scalar(engine, "SELECT crescita_luce_giorni FROM tpo.protocollo_versioni WHERE public_id='PV-000001'")
    changes = {"light_growth_days": light + 2}
    conn = _connect(engine)
    assert module.run(conn, name, changes, None, "x", None, True, today=TODAY, out=lines.append) == 0
    conn.close()
    after = _snapshot(engine)
    conn = _connect(engine)
    assert module.run(conn, name, changes, None, "x", None, True, today=TODAY, out=lines.append) == 2
    conn.close()
    assert "Nessuna differenza" in "\n".join(lines) and _snapshot(engine) == after


def test_refusals_write_nothing(harvest_environment):
    engine, _writer = harvest_environment
    module, lines, name = _module(), [], _variety(engine)
    before = _snapshot(engine)
    cases = [
        (name, {"light_growth_days": 19}, date(2026, 10, 1)),                # nel passato
        (name, {"light_growth_days": 19}, date(2026, 1, 1)),                 # non successiva alla validita'
        (name, {"light_growth_days": -1}, None),                             # durata negativa
        (name, {"harvest_min_lead_days": 5, "harvest_max_lead_days": 1}, None),   # lead min > max
        (name, {"seed_grams_per_set": 0}, None),                             # grammi <= 0
        (name, {"germination_days": 2.5}, None),                             # non intero
        ("Varieta inesistente", {"light_growth_days": 19}, None),
    ]
    for variety, changes, valid_from in cases:
        conn = _connect(engine)
        assert module.run(conn, variety, changes, valid_from, "x", None, True, today=TODAY, out=lines.append) == 2
        conn.close()
    assert "RIFIUTATO" in "\n".join(lines) and _snapshot(engine) == before


def test_unknown_parameter_is_refused(harvest_environment):
    engine, _writer = harvest_environment
    conn = _connect(engine)
    with pytest.raises(ProtocolRevisionError):
        prepare(conn.cursor(), _variety(engine), {"colore": "verde"}, TODAY, TODAY)
    conn.close()


def test_variety_name_matches_ignoring_case_and_accents(harvest_environment):
    engine, _writer = harvest_environment
    conn = _connect(engine)
    cursor = conn.cursor()
    assert current_version(cursor, _variety(engine).upper())["public_id"] == "PV-000001"
    conn.close()


def test_variety_can_be_given_by_its_traceability_code(harvest_environment):
    """17/10/2026: Matteo scrive LEN (codice di tracciabilita'), non il nome per esteso."""
    engine, _writer = harvest_environment
    code = scalar(engine, "SELECT codice_tracciabilita FROM tpo.varieta ORDER BY id LIMIT 1")
    conn = _connect(engine)
    cursor = conn.cursor()
    assert current_version(cursor, code.lower())["variety"] == _variety(engine)
    with pytest.raises(ProtocolRevisionError):
        current_version(cursor, code.lower() + "x")
    conn.close()
