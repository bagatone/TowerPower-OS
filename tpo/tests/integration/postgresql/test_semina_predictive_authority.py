"""Real PostgreSQL: commissioning governato dell'autorita' predittiva delle semine (addendum 6/10/2026)."""

from __future__ import annotations

import psycopg
import pytest

from src.tpo_core.infrastructure.postgresql import semina_predictive_authority as module
from tests.integration.postgresql.test_production_planning_end_to_end import _scalar, _seed_identity
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

PROV = '{"declared_sets":"OWNER_AUTHORIZED"}'


def _seed(engine, harvested: int = 0, grams: str = "10") -> None:
    _seed_identity(engine)
    with engine.begin() as c:
        c.exec_driver_sql("SET LOCAL session_replication_role = replica")
        c.exec_driver_sql(f"""
          INSERT INTO tpo.semine
            (public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,protocollo_versione_id,stato,
             quantita_seme,unita_misura,data_avvio,causa_origine,cultivar_snapshot,uso_produttivo_snapshot,
             lotto_seme_snapshot,protocollo_snapshot,created_by,codice_tracciabilita)
          SELECT 'SEM-000901',id,1,1,1,1,'CRESCITA',{grams},'GRAM',TIMESTAMPTZ '2026-08-01 06:00+00',
                 'PIANO_PRODUZIONE','x','x','x','x','test','HVT-0108-A' FROM tpo.varieta LIMIT 1""")
        if harvested:
            c.exec_driver_sql(f"""
              INSERT INTO tpo.raccolte (public_id,semina_id,data_raccolta,quantita,unita_misura,created_by)
              SELECT 'RAC-000901',id,TIMESTAMPTZ '2026-08-10 06:00+00',{harvested},'SET','test'
              FROM tpo.semine WHERE public_id='SEM-000901'""")


def _cursor(engine):
    url = engine.url
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)
    return conn, conn.cursor()


def _commission(cur, sets, **kw):
    return module.commission_predictive(cur, declared_sets=sets, actor="matteo", reason="test",
                                        correlation_id="corr", provenance=PROV, **kw)


def test_sets_are_never_computed_from_grams_and_must_be_declared(planning_database):
    engine = planning_database
    _seed(engine, grams="7")                      # 7 g: non corrisponde a SET interi del protocollo
    conn, cur = _cursor(engine)
    [(item, sets, derived, state)] = module.plan(cur, {})
    assert state == "SERVE_SET" and sets is None and derived is None
    [(_, sets, derived, state)] = module.plan(cur, {"SEM-000901": 1})
    assert state == "DA_COMPILARE" and sets == 1 and derived.quantity == 1 and derived.uom == "SET"
    assert (derived.window_end - derived.window_start).days == 5
    conn.close()


def test_commission_writes_all_four_fields_audit_and_bumps_version_then_replays(planning_database):
    engine = planning_database
    _seed(engine)
    before = _scalar(engine, "SELECT version FROM tpo.semine WHERE public_id='SEM-000901'")
    conn, cur = _cursor(engine)
    done, replays = _commission(cur, {"SEM-000901": 2})
    conn.commit()
    assert done == ("SEM-000901",) and replays == ()
    assert _scalar(engine, "SELECT version FROM tpo.semine WHERE public_id='SEM-000901'") == before + 1
    assert _scalar(engine, "SELECT expected_useful_quantity FROM tpo.semine WHERE public_id='SEM-000901'") == 2
    assert _scalar(engine, "SELECT harvest_window_end > harvest_window_start FROM tpo.semine "
                           "WHERE public_id='SEM-000901'") is True
    assert _scalar(engine, "SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='SEMINA' "
                           "AND entity_public_id='SEM-000901' AND operation='UPDATE' AND correlation_id='corr'") == 1
    done, replays = _commission(cur, {"SEM-000901": 2})          # stesso valore: replay compatibile
    assert done == () and replays == ("SEM-000901",)
    with pytest.raises(module.SeminaPredictiveAuthorityError, match="valori diversi"):
        _commission(cur, {"SEM-000901": 3})                      # correzione non supportata
    conn.rollback()
    conn.close()


def test_refuses_more_harvested_than_declared_and_invalid_sets(planning_database):
    engine = planning_database
    _seed(engine, harvested=3)
    conn, cur = _cursor(engine)
    with pytest.raises(module.SeminaPredictiveAuthorityError, match="gia' raccolti"):
        _commission(cur, {"SEM-000901": 2})
    for bad in (0, -1, 1.5):
        with pytest.raises(module.SeminaPredictiveAuthorityError):
            _commission(cur, {"SEM-000901": bad})
    with pytest.raises(module.SeminaPredictiveAuthorityError, match="inesistenti"):
        _commission(cur, {"SEM-999999": 1})
    conn.rollback()
    assert _scalar(engine, "SELECT expected_useful_quantity IS NULL FROM tpo.semine WHERE public_id='SEM-000901'")
    conn.close()
