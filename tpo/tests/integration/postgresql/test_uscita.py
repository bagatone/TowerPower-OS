from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
import uuid

from alembic import command as alembic_command
import psycopg
import pytest
import sqlalchemy as sa

from src.tpo_core.application.uscita.errors import (
    InvalidUscitaCommandError, UscitaIdempotencyConflictError,
    UscitaOriginalIsCorrectionError, UscitaOriginalNotFoundError,
)
from src.tpo_core.application.uscita.models import (
    CorreggiUscita, RegistraUscita, UscitaAuthority,
)
from src.tpo_core.domain.identifiers import ActorId, UscitaId
from src.tpo_core.domain.states import CategoriaUscita, MetodoPagamento
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.uscita import PostgreSQLUscitaWriter
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
    name = f"tpo_uscita_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as c:
        alembic_command.upgrade(make_config(connection=c), "head")
    try:
        yield engine, PostgreSQLUscitaWriter(_Factory(engine))
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def uscita(key="uscita-1", *, importo="45.50", data=date(2026, 9, 4),
           categoria=CategoriaUscita.SEMENTI, beneficiario="Vivai Canarias SL",
           metodo=MetodoPagamento.BONIFICO, note=None):
    return RegistraUscita(
        Decimal(importo), data, categoria, beneficiario, metodo,
        UscitaAuthority(ActorId("owner"), "expense paid", f"corr-{key}", key), note,
    )


def correction(key="fix-1", *, original="USC-000001", importo="-20.00",
               data=date(2026, 9, 4), categoria=CategoriaUscita.SEMENTI,
               beneficiario="Vivai Canarias SL", metodo=MetodoPagamento.BONIFICO,
               note=None):
    return CorreggiUscita(
        UscitaId(original), Decimal(importo), data, categoria, beneficiario, metodo,
        UscitaAuthority(ActorId("owner"), "correction", f"corr-{key}", key), note,
    )


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.exec_driver_sql(sql).scalar_one()


def test_blank_beneficiario_is_rejected_at_domain_layer():
    with pytest.raises(InvalidUscitaCommandError):
        uscita(beneficiario="   ")


def test_creation_multiple_replay_conflict_and_audit(environment):
    engine, writer = environment
    first = writer.record(uscita())
    replay = writer.record(uscita())
    second = writer.record(uscita("uscita-2", importo="12.00", categoria=CategoriaUscita.UTENZE))
    assert (first.uscita_id.value, second.uscita_id.value) == ("USC-000001", "USC-000002")
    assert replay.outcome == "COMPATIBLE_REPLAY" and replay.uscita_id == first.uscita_id
    with pytest.raises(UscitaIdempotencyConflictError):
        writer.record(uscita(importo="1.00"))
    with engine.connect() as connection:
        counts = connection.exec_driver_sql(
            "SELECT (SELECT count(*) FROM tpo.uscite),"
            "(SELECT count(*) FROM tpo.uscita_recording_requests WHERE outcome='COMMITTED'),"
            "(SELECT count(*) FROM tpo.audit_eventi "
            "WHERE entity_type='USCITA' AND operation='INSERT')"
        ).one()
    assert counts == (2, 2, 2)


def test_concurrent_identical_and_distinct_requests(environment):
    engine, writer = environment
    with ThreadPoolExecutor(max_workers=2) as pool:
        identical = list(pool.map(lambda _: writer.record(uscita("same")), range(2)))
    assert {r.uscita_id.value for r in identical} == {"USC-000001"}
    assert {r.outcome for r in identical} == {"INSERTED", "COMPATIBLE_REPLAY"}


def test_correction_creates_new_usc_linked_to_original(environment):
    engine, writer = environment
    original = writer.record(uscita())
    result = writer.correct(correction())
    assert result.uscita_id.value == "USC-000002"
    assert result.original_uscita_id == original.uscita_id
    assert result.importo == Decimal("-20.00")
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT r.importo,o.public_id FROM tpo.uscite r "
            "JOIN tpo.uscite o ON o.id=r.rettifica_uscita_id "
            "WHERE r.public_id='USC-000002'"
        ).one()
    assert row == (Decimal("-20.00"), "USC-000001")


def test_original_uscita_remains_unchanged_after_correction(environment):
    engine, writer = environment
    writer.record(uscita())
    writer.correct(correction())
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT importo,rettifica_uscita_id FROM tpo.uscite WHERE public_id='USC-000001'"
        ).one()
    assert row == (Decimal("45.50"), None)


def test_correction_may_reclassify_categoria_without_matching_original(environment):
    engine, writer = environment
    writer.record(uscita(categoria=CategoriaUscita.SEMENTI))
    result = writer.correct(correction(categoria=CategoriaUscita.ATTREZZATURA))
    assert result.categoria == CategoriaUscita.ATTREZZATURA
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT categoria FROM tpo.uscite WHERE public_id='USC-000002'"
        ).scalar_one()
    assert row == "ATTREZZATURA"


def test_original_not_found_fails_without_identity_consumption(environment):
    engine, writer = environment
    before = scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='USCITA_ID'"
    )
    with pytest.raises(UscitaOriginalNotFoundError):
        writer.correct(correction(original="USC-999999"))
    assert scalar(engine, "SELECT count(*) FROM tpo.uscite") == 0
    assert scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='USCITA_ID'"
    ) == before


def test_correction_of_correction_is_rejected(environment):
    engine, writer = environment
    writer.record(uscita())
    writer.correct(correction("first-fix"))
    with pytest.raises(UscitaOriginalIsCorrectionError):
        writer.correct(correction("chained-fix", original="USC-000002"))
    assert scalar(engine, "SELECT count(*) FROM tpo.uscite") == 2


def test_idempotent_replay_and_conflict_on_correction(environment):
    engine, writer = environment
    writer.record(uscita())
    first = writer.correct(correction())
    replay = writer.correct(correction())
    assert replay.outcome == "COMPATIBLE_REPLAY" and replay.uscita_id == first.uscita_id
    with pytest.raises(UscitaIdempotencyConflictError):
        writer.correct(correction(importo="-5.00"))
    assert scalar(engine, "SELECT count(*) FROM tpo.uscite") == 2


def test_multiple_corrections_on_same_original_are_allowed(environment):
    engine, writer = environment
    writer.record(uscita())
    first = writer.correct(correction("fix-a", importo="-10.00"))
    second = writer.correct(correction("fix-b", importo="-5.00"))
    assert first.uscita_id.value == "USC-000002"
    assert second.uscita_id.value == "USC-000003"
    assert scalar(engine, "SELECT count(*) FROM tpo.uscite") == 3


def test_database_immutability(environment):
    engine, writer = environment
    writer.record(uscita())
    for statement in (
        "UPDATE tpo.uscite SET importo=2 WHERE public_id='USC-000001'",
        "DELETE FROM tpo.uscite WHERE public_id='USC-000001'",
    ):
        with pytest.raises(
            sa.exc.DBAPIError, match="Uscita physical fact authority is immutable"
        ):
            with engine.begin() as connection:
                connection.exec_driver_sql(statement)
