from datetime import datetime, timezone
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.varieta_lettura.errors import VarietaLetturaVarietaNotFoundError
from src.tpo_core.application.varieta_lettura.models import (
    RichiediElencoVarieta, RichiediVarieta,
)
from src.tpo_core.domain.identifiers import VarietaId
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.varieta_lettura import (
    PostgreSQLVarietaLetturaReader,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def varieta_environment(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_varieta_lettura_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
        connection.exec_driver_sql(
            "INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,"
            "updated_at,updated_by) VALUES ('VAR-000001','Rucola','ATTIVA','test',%s,'test')",
            (NOW,),
        )
        connection.exec_driver_sql(
            "INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,"
            "updated_at,updated_by) VALUES "
            "('VAR-000002','Acetosella','IN_SPERIMENTAZIONE','test',%s,'test')",
            (NOW,),
        )
        varieta_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.varieta WHERE public_id='VAR-000001'"
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO tpo.listino_varieta(varieta_id,prezzo_unitario,aliquota_igic,"
            "created_at,created_by,updated_at,updated_by) "
            "VALUES (%s,3.50,7,%s,'test',%s,'test')",
            (varieta_pk, NOW, NOW),
        )
    return engine


def test_varieta_reads_row_with_prezzo(varieta_environment):
    reader = PostgreSQLVarietaLetturaReader(_Factory(varieta_environment))
    result = reader.varieta(RichiediVarieta(VarietaId("VAR-000001")))
    assert result.denominazione == "Rucola"
    assert result.prezzo_unitario == 3.50


def test_varieta_reads_row_without_prezzo(varieta_environment):
    reader = PostgreSQLVarietaLetturaReader(_Factory(varieta_environment))
    result = reader.varieta(RichiediVarieta(VarietaId("VAR-000002")))
    assert result.stato == "IN_SPERIMENTAZIONE"
    assert result.prezzo_unitario is None


def test_varieta_raises_when_not_found(varieta_environment):
    reader = PostgreSQLVarietaLetturaReader(_Factory(varieta_environment))
    with pytest.raises(VarietaLetturaVarietaNotFoundError):
        reader.varieta(RichiediVarieta(VarietaId("VAR-000099")))


def test_elenco_orders_by_denominazione(varieta_environment):
    reader = PostgreSQLVarietaLetturaReader(_Factory(varieta_environment))
    result = reader.elenco(RichiediElencoVarieta())
    nomi = [v.denominazione for v in result.varieta]
    assert nomi == ["Acetosella", "Rucola"]
