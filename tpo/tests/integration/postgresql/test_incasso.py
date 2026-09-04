from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
import uuid

from alembic import command as alembic_command
import psycopg
import pytest
import sqlalchemy as sa

from src.tpo_core.application.incasso.errors import (
    IncassoCorrectionFatturaMismatchError, IncassoFatturaNotFoundError,
    IncassoIdempotencyConflictError, IncassoOriginalIsCorrectionError,
    IncassoOriginalNotFoundError,
)
from src.tpo_core.application.incasso.models import (
    CorreggiIncasso, IncassoAuthority, RegistraIncasso,
)
from src.tpo_core.domain.identifiers import ActorId, IncassoId, NumeroFattura
from src.tpo_core.domain.states import MetodoPagamento
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.incasso import PostgreSQLIncassoWriter
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)


class _Factory:
    def __init__(self, engine) -> None:
        self.url = engine.url

    def connect(self):
        return psycopg.connect(
            host=self.url.host, port=self.url.port, dbname=self.url.database,
            user=self.url.username, connect_timeout=5,
        )


@pytest.fixture
def environment(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_incasso_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as c:
        alembic_command.upgrade(make_config(connection=c), "head")
        c.exec_driver_sql("""
            INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
            VALUES ('CLI-000001','Cliente Test','test',CURRENT_TIMESTAMP,'test')
        """)
        for numero in ("2026/0001", "2026/0002"):
            c.exec_driver_sql(
                """INSERT INTO tpo.fatture
                     (numero_fattura,cliente_id,data_emissione,scadenza,totale_netto,
                      totale_igic,totale,created_by,created_at)
                   SELECT %s,id,DATE '2026-09-01',DATE '2026-10-01',100.00,7.00,107.00,
                          'test',CURRENT_TIMESTAMP
                   FROM tpo.clienti WHERE public_id='CLI-000001'""",
                (numero,),
            )
    try:
        yield engine, PostgreSQLIncassoWriter(_Factory(engine))
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def incasso(key="incasso-1", *, fattura="2026/0001", importo="107.40",
            data=date(2026, 9, 4), metodo=MetodoPagamento.BONIFICO, note=None):
    return RegistraIncasso(
        NumeroFattura(fattura), Decimal(importo), data, metodo,
        IncassoAuthority(ActorId("owner"), "payment received", f"corr-{key}", key), note,
    )


def correction(key="fix-1", *, original="INC-000001", fattura="2026/0001",
               importo="-50.00", data=date(2026, 9, 4), metodo=MetodoPagamento.BONIFICO,
               note=None):
    return CorreggiIncasso(
        IncassoId(original), NumeroFattura(fattura), Decimal(importo), data, metodo,
        IncassoAuthority(ActorId("owner"), "correction", f"corr-{key}", key), note,
    )


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.exec_driver_sql(sql).scalar_one()


def test_missing_fattura_fails_without_identity_consumption(environment):
    engine, writer = environment
    before = scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='INCASSO_ID'"
    )
    with pytest.raises(IncassoFatturaNotFoundError):
        writer.record(incasso(fattura="2099/9999"))
    assert scalar(engine, "SELECT count(*) FROM tpo.incassi") == 0
    assert scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='INCASSO_ID'"
    ) == before


def test_creation_multiple_replay_conflict_and_audit(environment):
    engine, writer = environment
    first = writer.record(incasso())
    replay = writer.record(incasso())
    second = writer.record(incasso("incasso-2", importo="53.50", fattura="2026/0002"))
    assert (first.incasso_id.value, second.incasso_id.value) == ("INC-000001", "INC-000002")
    assert replay.outcome == "COMPATIBLE_REPLAY" and replay.incasso_id == first.incasso_id
    with pytest.raises(IncassoIdempotencyConflictError):
        writer.record(incasso(importo="1.00"))
    with engine.connect() as connection:
        counts = connection.exec_driver_sql(
            "SELECT (SELECT count(*) FROM tpo.incassi),"
            "(SELECT count(*) FROM tpo.incasso_recording_requests WHERE outcome='COMMITTED'),"
            "(SELECT count(*) FROM tpo.audit_eventi "
            "WHERE entity_type='INCASSO' AND operation='INSERT')"
        ).one()
    assert counts == (2, 2, 2)


def test_concurrent_identical_and_distinct_requests(environment):
    engine, writer = environment
    with ThreadPoolExecutor(max_workers=2) as pool:
        identical = list(pool.map(lambda _: writer.record(incasso("same")), range(2)))
    assert {r.incasso_id.value for r in identical} == {"INC-000001"}
    assert {r.outcome for r in identical} == {"INSERTED", "COMPATIBLE_REPLAY"}


def test_correction_creates_new_inc_linked_to_original(environment):
    engine, writer = environment
    original = writer.record(incasso())
    result = writer.correct(correction())
    assert result.incasso_id.value == "INC-000002"
    assert result.original_incasso_id == original.incasso_id
    assert result.importo == Decimal("-50.00")
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT r.importo,o.public_id FROM tpo.incassi r "
            "JOIN tpo.incassi o ON o.id=r.rettifica_incasso_id "
            "WHERE r.public_id='INC-000002'"
        ).one()
    assert row == (Decimal("-50.00"), "INC-000001")


def test_original_incasso_remains_unchanged_after_correction(environment):
    engine, writer = environment
    writer.record(incasso())
    writer.correct(correction())
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT importo,rettifica_incasso_id FROM tpo.incassi WHERE public_id='INC-000001'"
        ).one()
    assert row == (Decimal("107.40"), None)


def test_original_not_found_fails_without_identity_consumption(environment):
    engine, writer = environment
    before = scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='INCASSO_ID'"
    )
    with pytest.raises(IncassoOriginalNotFoundError):
        writer.correct(correction(original="INC-999999"))
    assert scalar(engine, "SELECT count(*) FROM tpo.incassi") == 0
    assert scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='INCASSO_ID'"
    ) == before


def test_correction_of_correction_is_rejected(environment):
    engine, writer = environment
    writer.record(incasso())
    writer.correct(correction("first-fix"))
    with pytest.raises(IncassoOriginalIsCorrectionError):
        writer.correct(correction("chained-fix", original="INC-000002"))
    assert scalar(engine, "SELECT count(*) FROM tpo.incassi") == 2


def test_fattura_mismatch_is_rejected_without_identity_consumption(environment):
    engine, writer = environment
    writer.record(incasso(fattura="2026/0001"))
    before = scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='INCASSO_ID'"
    )
    with pytest.raises(IncassoCorrectionFatturaMismatchError):
        writer.correct(correction(fattura="2026/0002"))
    assert scalar(engine, "SELECT count(*) FROM tpo.incassi") == 1
    assert scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='INCASSO_ID'"
    ) == before


def test_idempotent_replay_and_conflict_on_correction(environment):
    engine, writer = environment
    writer.record(incasso())
    first = writer.correct(correction())
    replay = writer.correct(correction())
    assert replay.outcome == "COMPATIBLE_REPLAY" and replay.incasso_id == first.incasso_id
    with pytest.raises(IncassoIdempotencyConflictError):
        writer.correct(correction(importo="-10.00"))
    assert scalar(engine, "SELECT count(*) FROM tpo.incassi") == 2


def test_multiple_corrections_on_same_original_are_allowed(environment):
    engine, writer = environment
    writer.record(incasso())
    first = writer.correct(correction("fix-a", importo="-20.00"))
    second = writer.correct(correction("fix-b", importo="-10.00"))
    assert first.incasso_id.value == "INC-000002"
    assert second.incasso_id.value == "INC-000003"
    assert scalar(engine, "SELECT count(*) FROM tpo.incassi") == 3


def test_database_immutability(environment):
    engine, writer = environment
    writer.record(incasso())
    for statement in (
        "UPDATE tpo.incassi SET importo=2 WHERE public_id='INC-000001'",
        "DELETE FROM tpo.incassi WHERE public_id='INC-000001'",
    ):
        with pytest.raises(
            sa.exc.DBAPIError, match="Incasso physical fact authority is immutable"
        ):
            with engine.begin() as connection:
                connection.exec_driver_sql(statement)
