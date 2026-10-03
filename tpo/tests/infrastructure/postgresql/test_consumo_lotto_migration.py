"""Migrazione 20261002_0036 (CONSUMO_LOTTO) su PostgreSQL reale: backfill storico.

Il database nasce alla revisione precedente (20260919_0035), vengono scritti
MOVIMENTI storici reali (CARICO/SCARICO senza alcun consumo registrato), poi si
applica la 0036 e si verifica che il backfill pre-consumi i CARICO piu' vecchi
(FIFO) con l'esatto totale gia' scaricato, senza mai eccedere la quantita' di un
CARICO e senza attribuire nulla a una CONSEGNA specifica.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.infrastructure.postgresql.alembic import make_config
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    migration_postgresql, writer_postgresql_cluster_engine,
)

TZ = ZoneInfo("Atlantic/Canary")
WHEN = datetime(2026, 9, 1, 8, tzinfo=TZ)


def _engine_at(admin_engine, revision: str):
    """Database usa-e-getta migrato fino a ``revision`` (generatore)."""
    database_name = f"tpo_consumo_{uuid.uuid4().hex}"
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    engine = sa.create_engine(admin_engine.url.set(database=database_name))
    try:
        with engine.connect() as connection:
            alembic_command.upgrade(make_config(connection=connection), revision)
            connection.commit()
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')


@pytest.fixture
def pre_0036_engine(writer_postgresql_cluster_engine):
    yield from _engine_at(writer_postgresql_cluster_engine, "20260919_0035")


@pytest.fixture
def at_0036_engine(writer_postgresql_cluster_engine):
    yield from _engine_at(writer_postgresql_cluster_engine, "20261002_0036")


def _variety(connection, number: int) -> int:
    return connection.exec_driver_sql("""
      INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,updated_at,updated_by)
      VALUES (%s,%s,'ATTIVA','test',now(),'test') RETURNING id
    """, (f"VAR-{number:06d}", f"Variety {number}")).scalar_one()


def _movement(connection, variety_pk: int, public_number: int, tipo: str, quantity: str,
              hour: int, unit: str = "SET") -> None:
    direction = "POSITIVO" if tipo == "CARICO" else "NEGATIVO"
    connection.exec_driver_sql("""
      INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at)
      VALUES (%s,0,%s,now()) ON CONFLICT DO NOTHING
    """, (variety_pk, unit))
    connection.exec_driver_sql("""
      INSERT INTO tpo.movimenti_magazzino
        (public_id,varieta_id,unita_misura,tipo,direzione,quantita,data_movimento,
         motivo,origine_tipo,created_at,created_by)
      VALUES (%s,%s,%s,%s,%s,%s,%s,'seed storico','TEST_SEED',now(),'test')
    """, (f"MOV-{public_number:06d}", variety_pk, unit, tipo, direction, quantity,
          WHEN.replace(hour=hour)))


def _upgrade_head(engine) -> None:
    with engine.connect() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
        connection.commit()


def _backfill(engine) -> list[tuple[str, str, Decimal]]:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("""
          SELECT m.public_id, cl.tipo_consumo::text, cl.quantita
          FROM tpo.consumi_lotto cl JOIN tpo.movimenti_magazzino m ON m.id = cl.movimento_carico_id
          ORDER BY m.public_id
        """).all()
        return [(r[0], r[1], r[2]) for r in rows]


def test_backfill_preconsumes_oldest_carichi_fifo(pre_0036_engine) -> None:
    with pre_0036_engine.begin() as connection:
        variety = _variety(connection, 940001)
        _movement(connection, variety, 940101, "CARICO", "2", 8)
        _movement(connection, variety, 940102, "CARICO", "5", 9)
        _movement(connection, variety, 940201, "SCARICO", "1", 10)
        _movement(connection, variety, 940202, "SCARICO", "2", 11)
    _upgrade_head(pre_0036_engine)
    # scaricato storico 3 SET -> 2 dal CARICO piu' vecchio, 1 dal successivo
    assert _backfill(pre_0036_engine) == [
        ("MOV-940101", "BACKFILL_STORICO", Decimal("2")),
        ("MOV-940102", "BACKFILL_STORICO", Decimal("1")),
    ]


def test_backfill_never_exceeds_carichi_when_scaricato_is_larger(pre_0036_engine) -> None:
    """Scarichi storici oltre i CARICO tracciabili (giacenza senza origine):
    il backfill consuma al massimo cio' che i CARICO hanno portato e la
    migrazione non fallisce."""
    with pre_0036_engine.begin() as connection:
        variety = _variety(connection, 940002)
        _movement(connection, variety, 940301, "CARICO", "1", 8)
        _movement(connection, variety, 940401, "SCARICO", "4", 10)
    _upgrade_head(pre_0036_engine)
    assert _backfill(pre_0036_engine) == [("MOV-940301", "BACKFILL_STORICO", Decimal("1"))]


def test_backfill_is_per_variety_and_unit_and_ignores_untouched_carichi(pre_0036_engine) -> None:
    """Un CARICO in GRAM non viene consumato da uno SCARICO in SET (la
    situazione reale di Afila/Cilantro), e una VARIETA senza scarichi non
    riceve nessun consumo."""
    with pre_0036_engine.begin() as connection:
        gram_variety = _variety(connection, 940003)
        _movement(connection, gram_variety, 940501, "CARICO", "933", 8, unit="GRAM")
        _movement(connection, gram_variety, 940601, "SCARICO", "1", 10, unit="SET")
        idle_variety = _variety(connection, 940004)
        _movement(connection, idle_variety, 940701, "CARICO", "3", 8)
    _upgrade_head(pre_0036_engine)
    assert _backfill(pre_0036_engine) == []


def test_downgrade_removes_only_the_consumo_lotto_objects(pre_0036_engine) -> None:
    _upgrade_head(pre_0036_engine)
    with pre_0036_engine.connect() as connection:
        alembic_command.downgrade(make_config(connection=connection), "20260919_0035")
        connection.commit()
        assert connection.exec_driver_sql(
            "SELECT to_regclass('tpo.consumi_lotto')"
        ).scalar_one() is None
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == "20260919_0035"
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
            "WHERE n.nspname='tpo' AND t.typname='consumo_lotto_tipo'"
        ).scalar_one() == 0


def _gram_carico_with_set_raccolta(connection, variety_pk: int, number: int,
                                   raccolta_set: str, grams: str, hour: int) -> int:
    """CARICO storico in GRAM legato a una RACCOLTA in SET (caso Afila/Cilantro).
    Le chiavi esterne sono sospese solo per la riga RACCOLTA (la SEMINA non
    serve a questi test)."""
    connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
    raccolta_pk = connection.exec_driver_sql("""
      INSERT INTO tpo.raccolte(public_id,semina_id,data_raccolta,quantita,unita_misura,created_by)
      VALUES (%s,1,%s,%s,'SET','test') RETURNING id
    """, (f"RAC-{number:06d}", WHEN.replace(hour=hour), raccolta_set)).scalar_one()
    connection.exec_driver_sql("""
      INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at)
      VALUES (%s,0,'GRAM',now()) ON CONFLICT DO NOTHING
    """, (variety_pk,))
    connection.exec_driver_sql("""
      INSERT INTO tpo.movimenti_magazzino
        (public_id,varieta_id,unita_misura,tipo,direzione,quantita,data_movimento,
         motivo,origine_tipo,raccolta_id,created_at,created_by)
      VALUES (%s,%s,'GRAM','CARICO','POSITIVO',%s,%s,'carico storico','RACCOLTA',%s,now(),'test')
    """, (f"MOV-{number:06d}", variety_pk, grams, WHEN.replace(hour=hour), raccolta_pk))
    connection.exec_driver_sql("SET LOCAL session_replication_role = origin")
    return raccolta_pk


def test_0037_backfill_attributes_set_scarichi_to_gram_carichi_via_raccolta(at_0036_engine) -> None:
    """Dati reali di Afila: CARICO 622 g (RACCOLTA 2 SET, 17/9) e 311 g
    (RACCOLTA 1 SET, 18/9), 1 SET gia' consegnato. Dopo la 0037 il SET storico
    consegnato e' pre-consumato dal lotto piu' vecchio (1 SET su 2): restano
    2 SET tracciabili = lo stock reale."""
    with at_0036_engine.begin() as connection:
        variety = _variety(connection, 950001)
        _gram_carico_with_set_raccolta(connection, variety, 950101, "2", "622", 8)
        _gram_carico_with_set_raccolta(connection, variety, 950102, "1", "311", 9)
        _movement(connection, variety, 950201, "SCARICO", "1", 10, unit="SET")
    # la 0036 non puo' aver spiegato nulla: carichi in GRAM, scarico in SET
    assert _backfill(at_0036_engine) == []
    _upgrade_head(at_0036_engine)
    assert _backfill(at_0036_engine) == [("MOV-950101", "BACKFILL_STORICO", Decimal("1"))]


def test_0037_replaces_0036_backfill_rows_computed_in_wrong_unit(at_0036_engine) -> None:
    """Se la 0036 aveva pre-consumato un CARICO in GRAM contro uno scarico in
    GRAM (unita' del movimento), la 0037 rimuove quella riga e ricalcola nella
    unita' di tracciabilita' (SET della RACCOLTA)."""
    with at_0036_engine.begin() as connection:
        variety = _variety(connection, 950002)
        raccolta_pk = _gram_carico_with_set_raccolta(connection, variety, 950301, "2", "622", 8)
        _movement(connection, variety, 950401, "SCARICO", "1", 10, unit="SET")
        carico_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.movimenti_magazzino WHERE public_id='MOV-950301'"
        ).scalar_one()
        connection.exec_driver_sql("""
          INSERT INTO tpo.consumi_lotto
            (movimento_carico_id, movimento_scarico_id, tipo_consumo, quantita, created_at, created_by)
          VALUES (%s, NULL, 'BACKFILL_STORICO', 500, now(), 'migration-20261002-0036-backfill-storico')
        """, (carico_pk,))
    _upgrade_head(at_0036_engine)
    assert _backfill(at_0036_engine) == [("MOV-950301", "BACKFILL_STORICO", Decimal("1"))]


def test_0037_bounds_use_raccolta_capacity_and_downgrade_restores_0036(at_0036_engine) -> None:
    with at_0036_engine.begin() as connection:
        variety = _variety(connection, 950003)
        _gram_carico_with_set_raccolta(connection, variety, 950501, "2", "622", 8)
        _movement(connection, variety, 950601, "SCARICO", "1", 10, unit="SET")
    _upgrade_head(at_0036_engine)
    with at_0036_engine.connect() as connection:
        carico_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.movimenti_magazzino WHERE public_id='MOV-950501'").scalar_one()
        scarico_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.movimenti_magazzino WHERE public_id='MOV-950601'").scalar_one()
        connection.rollback()
        # Capacita' = 2 SET della RACCOLTA (non 622 g); il backfill ne ha gia'
        # consumato 1: altri 2 superano la capacita', altri 1 no.
        trans = connection.begin()
        connection.exec_driver_sql("""
          INSERT INTO tpo.consumi_lotto
            (movimento_carico_id, movimento_scarico_id, tipo_consumo, quantita, created_at, created_by)
          VALUES (%s,%s,'CONSEGNA',2,now(),'test')
        """, (carico_pk, scarico_pk))
        with pytest.raises(sa.exc.DBAPIError, match="ct_consumi_lotto_carico_bounds violated"):
            connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
        trans.rollback()
        # 1 SET invece e' ammesso (scarico in SET = unita' di tracciabilita' del lotto)
        connection.exec_driver_sql("""
          INSERT INTO tpo.consumi_lotto
            (movimento_carico_id, movimento_scarico_id, tipo_consumo, quantita, created_at, created_by)
          VALUES (%s,%s,'CONSEGNA',1,now(),'test')
        """, (carico_pk, scarico_pk))
        connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
        connection.rollback()
    with at_0036_engine.connect() as connection:
        alembic_command.downgrade(make_config(connection=connection), "20261002_0036")
        connection.commit()
        definition = connection.exec_driver_sql(
            "SELECT pg_get_functiondef('tpo.fn_check_consumo_lotto_bounds(bigint,bigint)'::regprocedure)"
        ).scalar_one()
        assert "tu_uom" not in definition
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.consumi_lotto WHERE created_by LIKE 'migration-20261003-0037%%'"
        ).scalar_one() == 0
