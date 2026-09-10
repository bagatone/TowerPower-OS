from datetime import datetime, timezone
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.clienti_lettura.errors import ClientiLetturaClienteNotFoundError
from src.tpo_core.application.clienti_lettura.models import (
    RichiediCliente, RichiediElencoClienti,
)
from src.tpo_core.domain.identifiers import ClienteId
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.clienti_lettura import (
    PostgreSQLClientiLetturaReader,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def clienti_environment(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_clienti_lettura_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
        connection.exec_driver_sql(
            "INSERT INTO tpo.clienti(public_id,denominazione,modalita_fatturazione,"
            "termini_pagamento_giorni,created_by,updated_at,updated_by) "
            "VALUES ('CLI-000002','Sal y Mar','PERIODICA_MENSILE',30,'test',%s,'test')", (NOW,),
        )
        connection.exec_driver_sql(
            "INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by) "
            "VALUES ('CLI-000001','Bahia Real','test',%s,'test')", (NOW,),
        )
    return engine


def test_cliente_reads_single_row_with_null_billing_fields(clienti_environment):
    reader = PostgreSQLClientiLetturaReader(_Factory(clienti_environment))
    result = reader.cliente(RichiediCliente(ClienteId("CLI-000001")))
    assert result.cliente_id == ClienteId("CLI-000001")
    assert result.denominazione == "Bahia Real"
    assert result.modalita_fatturazione is None
    assert result.termini_pagamento_giorni is None


def test_cliente_reads_billing_fields_when_set(clienti_environment):
    reader = PostgreSQLClientiLetturaReader(_Factory(clienti_environment))
    result = reader.cliente(RichiediCliente(ClienteId("CLI-000002")))
    assert result.modalita_fatturazione == "PERIODICA_MENSILE"
    assert result.termini_pagamento_giorni == 30


def test_cliente_raises_when_not_found(clienti_environment):
    reader = PostgreSQLClientiLetturaReader(_Factory(clienti_environment))
    with pytest.raises(ClientiLetturaClienteNotFoundError):
        reader.cliente(RichiediCliente(ClienteId("CLI-000099")))


def test_elenco_orders_by_denominazione(clienti_environment):
    reader = PostgreSQLClientiLetturaReader(_Factory(clienti_environment))
    result = reader.elenco(RichiediElencoClienti())
    nomi = [c.denominazione for c in result.clienti]
    assert nomi == ["Bahia Real", "Sal y Mar"]
