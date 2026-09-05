import uuid

import sqlalchemy as sa
from alembic import command as alembic_command
import pytest

from src.tpo_core.application.articolo.errors import ArticoloIdempotencyConflictError
from src.tpo_core.application.articolo.models import (
    ArticoloCommissioningAuthority, CommissionArticolo,
)
from src.tpo_core.domain.identifiers import ActorId
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.articolo import PostgreSQLArticoloWriter
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)


def commission(*, denominazione="Substrato fibra di cocco", unita_misura="GRAM", key="art-1"):
    return CommissionArticolo(
        denominazione=denominazione,
        unita_misura=unita_misura,
        authority=ArticoloCommissioningAuthority(
            ActorId("magazziniere"), "nuovo materiale", f"corr-{key}", key,
        ),
    )


@pytest.fixture
def articolo_environment(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_articolo_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
    return engine


def test_commission_articolo_creates_row_and_allocates_identity(articolo_environment):
    engine = articolo_environment
    writer = PostgreSQLArticoloWriter(_Factory(engine))
    result = writer.commission(commission())
    assert result.outcome == "INSERTED"
    assert result.articolo_id.value.startswith("ART-")
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT denominazione,unita_misura FROM tpo.articoli WHERE public_id=%s",
            (result.articolo_id.value,),
        ).fetchone()
        assert row[0] == "Substrato fibra di cocco"
        assert row[1] == "GRAM"
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='ARTICOLO' "
            "AND entity_public_id=%s AND operation='INSERT'",
            (result.articolo_id.value,),
        ).scalar_one() == 1


def test_multiple_commissions_allocate_distinct_identities(articolo_environment):
    engine = articolo_environment
    writer = PostgreSQLArticoloWriter(_Factory(engine))
    first = writer.commission(commission(key="k1"))
    second = writer.commission(commission(denominazione="Vaso biodegradabile", key="k2"))
    assert first.articolo_id != second.articolo_id


def test_idempotent_replay_returns_same_articolo(articolo_environment):
    engine = articolo_environment
    writer = PostgreSQLArticoloWriter(_Factory(engine))
    first = writer.commission(commission(key="shared-key"))
    replay = writer.commission(commission(key="shared-key"))
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert replay.articolo_id == first.articolo_id


def test_rejects_idempotency_key_reused_with_different_payload(articolo_environment):
    engine = articolo_environment
    writer = PostgreSQLArticoloWriter(_Factory(engine))
    writer.commission(commission(key="conflict-key"))
    with pytest.raises(ArticoloIdempotencyConflictError):
        writer.commission(commission(key="conflict-key", denominazione="Altro materiale"))
