"""Integrazione PostgreSQL reale per la governance di LISTINO_VARIETA.

Autorità: docs/architecture/LISTINO_VARIETA_GOVERNANCE_FREEZE.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from alembic import command as alembic_command
import psycopg
import pytest
import sqlalchemy as sa

from src.tpo_core.application.listino_varieta.errors import (
    InvalidListinoVarietaCommandError, ListinoVarietaVarietaNotFoundError,
)
from src.tpo_core.application.listino_varieta.models import (
    ImpostaPrezzoListinoVarieta, ListinoVarietaAuthority,
)
from src.tpo_core.domain.identifiers import ActorId, VarietaId
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.fatturazione_configuration import (
    PostgreSQLListinoVarietaWriter,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql as migration_postgresql,
)

NOW = datetime(2099, 1, 1, 10, tzinfo=timezone.utc)  # far future: always >= server now()


class _Factory:
    def __init__(self, engine) -> None:
        self.url = engine.url

    def connect(self):
        return psycopg.connect(
            host=self.url.host, port=self.url.port, dbname=self.url.database,
            user=self.url.username, connect_timeout=5,
        )


@pytest.fixture(scope="module")
def listino_cluster_engine(migration_postgresql):
    return migration_postgresql.engine


@pytest.fixture
def listino_environment(listino_cluster_engine):
    admin_engine = listino_cluster_engine
    database_name = f"tpo_listino_{uuid.uuid4().hex}"
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    engine = sa.create_engine(admin_engine.url.set(database=database_name))
    try:
        with engine.connect() as connection:
            alembic_command.upgrade(make_config(connection=connection), "head")
            connection.exec_driver_sql(
                """INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,
                     updated_at,updated_by)
                   VALUES ('VAR-000001','Cilantro','ATTIVA','listino-test',%s,'listino-test')""",
                (NOW,),
            )
            connection.commit()
        writer = PostgreSQLListinoVarietaWriter(_Factory(engine))
        yield engine, writer
    finally:
        engine.dispose()
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')


def authority(*, actor="owner", reason="Aggiornamento listino reale", correlation_id="corr-1"):
    return ListinoVarietaAuthority(ActorId(actor), reason, correlation_id)


def command(*, varieta="VAR-000001", prezzo="12.50", aliquota="7.00", auth=None):
    return ImpostaPrezzoListinoVarieta(
        VarietaId(varieta), Decimal(prezzo), Decimal(aliquota), auth or authority(),
    )


def fetch_listino(engine, varieta_public_id="VAR-000001"):
    with engine.connect() as connection:
        return connection.exec_driver_sql(
            """SELECT lv.prezzo_unitario,lv.aliquota_igic,lv.updated_by
               FROM tpo.listino_varieta lv
               JOIN tpo.varieta v ON v.id=lv.varieta_id WHERE v.public_id=%s""",
            (varieta_public_id,),
        ).one_or_none()


def fetch_audit_events(engine, varieta_public_id="VAR-000001"):
    with engine.connect() as connection:
        return connection.exec_driver_sql(
            """SELECT actor,operation,reason,before_data,after_data,correlation_id
               FROM tpo.audit_eventi
               WHERE entity_type='LISTINO_VARIETA' AND entity_public_id=%s
               ORDER BY id""",
            (varieta_public_id,),
        ).all()


def test_first_price_setting_has_no_before_data_and_one_audit_event(listino_environment):
    engine, writer = listino_environment
    result = writer.imposta_prezzo(command())
    assert result.varieta_public_id == "VAR-000001"
    assert result.prezzo_unitario == Decimal("12.50")
    assert result.aliquota_igic == Decimal("7.00")
    assert result.inserted is True
    assert result.updated is False
    assert result.outcome == "INSERTED"

    row = fetch_listino(engine)
    assert row == (Decimal("12.50"), Decimal("7.00"), "owner")

    events = fetch_audit_events(engine)
    assert len(events) == 1
    actor, operation, reason, before_data, after_data, correlation_id = events[0]
    assert actor == "owner"
    assert operation == "UPDATE"
    assert reason == "Aggiornamento listino reale"
    assert before_data is None
    assert after_data == {"prezzo_unitario": "12.5000", "aliquota_igic": "7.00"}
    assert correlation_id == "corr-1"


def test_subsequent_update_captures_previous_values_as_before_data(listino_environment):
    engine, writer = listino_environment
    writer.imposta_prezzo(command(prezzo="12.50", aliquota="7.00"))
    result = writer.imposta_prezzo(
        command(prezzo="15.00", aliquota="9.50",
                auth=authority(reason="Aumento prezzo stagionale", correlation_id="corr-2")),
    )
    assert result.inserted is False
    assert result.updated is True
    assert result.outcome == "UPDATED"

    row = fetch_listino(engine)
    assert row == (Decimal("15.00"), Decimal("9.50"), "owner")

    events = fetch_audit_events(engine)
    assert len(events) == 2
    second = events[1]
    actor, operation, reason, before_data, after_data, correlation_id = second
    assert operation == "UPDATE"
    assert reason == "Aumento prezzo stagionale"
    assert before_data == {"prezzo_unitario": "12.5000", "aliquota_igic": "7.00"}
    assert after_data == {"prezzo_unitario": "15.0000", "aliquota_igic": "9.50"}
    assert correlation_id == "corr-2"


def test_setting_same_price_twice_produces_two_audit_events_not_a_conflict(listino_environment):
    engine, writer = listino_environment
    writer.imposta_prezzo(command())
    result = writer.imposta_prezzo(
        command(auth=authority(reason="Riconferma prezzo", correlation_id="corr-2")),
    )
    assert result.updated is True
    events = fetch_audit_events(engine)
    assert len(events) == 2
    assert events[0][4] == events[1][4] == {"prezzo_unitario": "12.5000", "aliquota_igic": "7.00"}
    assert events[1][3] == {"prezzo_unitario": "12.5000", "aliquota_igic": "7.00"}


def test_missing_varieta_raises_typed_error_without_writes_or_audit(listino_environment):
    engine, writer = listino_environment
    with pytest.raises(ListinoVarietaVarietaNotFoundError):
        writer.imposta_prezzo(command(varieta="VAR-999999"))
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.listino_varieta"
        ).scalar_one() == 0
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='LISTINO_VARIETA'"
        ).scalar_one() == 0


def test_missing_varieta_leaves_no_partial_transaction_state(listino_environment):
    engine, writer = listino_environment
    writer.imposta_prezzo(command())
    with pytest.raises(ListinoVarietaVarietaNotFoundError):
        writer.imposta_prezzo(command(varieta="VAR-999999"))
    row = fetch_listino(engine)
    assert row == (Decimal("12.50"), Decimal("7.00"), "owner")
    assert len(fetch_audit_events(engine)) == 1


def test_authority_rejects_blank_reason_before_touching_db(listino_environment):
    engine, writer = listino_environment
    with pytest.raises(InvalidListinoVarietaCommandError):
        command(auth=authority(reason="  "))
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.listino_varieta"
        ).scalar_one() == 0


def test_authority_rejects_blank_correlation_id_before_touching_db(listino_environment):
    engine, writer = listino_environment
    with pytest.raises(InvalidListinoVarietaCommandError):
        command(auth=authority(correlation_id=""))
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.listino_varieta"
        ).scalar_one() == 0
