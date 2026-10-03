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


@pytest.fixture
def pre_0036_engine(writer_postgresql_cluster_engine):
    admin_engine = writer_postgresql_cluster_engine
    database_name = f"tpo_consumo_{uuid.uuid4().hex}"
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    engine = sa.create_engine(admin_engine.url.set(database=database_name))
    try:
        with engine.connect() as connection:
            alembic_command.upgrade(make_config(connection=connection), "20260919_0035")
            connection.commit()
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')


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
