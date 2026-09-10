from datetime import datetime, timezone
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.semente_lettura.errors import SementeLetturaLottoNotFoundError
from src.tpo_core.application.semente_lettura.models import (
    RichiediElencoLotti, RichiediElencoSementi, RichiediLotto,
)
from src.tpo_core.domain.identifiers import LottoSemeId
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.semente_lettura import (
    PostgreSQLSementeLetturaReader,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def semente_environment(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_semente_lettura_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
        semente_pk = connection.exec_driver_sql(
            "INSERT INTO tpo.sementi(fornitore,referenza_commerciale,created_by,"
            "updated_at,updated_by) VALUES ('Rijk Zwaan','RZ-CIL-01','test',%s,'test') "
            "RETURNING id", (NOW,),
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO tpo.lotti_seme(public_id,semente_id,numero_lotto_produttore,"
            "data_ricezione,quantita_iniziale,quantita_residua,unita_misura,created_by,"
            "updated_at,updated_by) VALUES "
            "('LSE-000001',%s,'NUM-2026-01',DATE '2026-01-01',1000,600,'GRAM','test',%s,'test')",
            (semente_pk, NOW),
        )
    return engine


def test_elenco_sementi_reads_catalog(semente_environment):
    reader = PostgreSQLSementeLetturaReader(_Factory(semente_environment))
    result = reader.elenco_sementi(RichiediElencoSementi())
    assert len(result.sementi) == 1
    assert result.sementi[0].fornitore == "Rijk Zwaan"


def test_lotto_reads_single_row_with_semente_joined(semente_environment):
    reader = PostgreSQLSementeLetturaReader(_Factory(semente_environment))
    result = reader.lotto(RichiediLotto(LottoSemeId("LSE-000001")))
    assert result.semente_fornitore == "Rijk Zwaan"
    assert result.quantita_residua == 600


def test_lotto_raises_when_not_found(semente_environment):
    reader = PostgreSQLSementeLetturaReader(_Factory(semente_environment))
    with pytest.raises(SementeLetturaLottoNotFoundError):
        reader.lotto(RichiediLotto(LottoSemeId("LSE-999999")))


def test_elenco_lotti_reads_all(semente_environment):
    reader = PostgreSQLSementeLetturaReader(_Factory(semente_environment))
    result = reader.elenco_lotti(RichiediElencoLotti())
    assert len(result.lotti) == 1
