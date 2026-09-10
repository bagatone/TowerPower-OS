from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.magazzino_lettura.models import (
    RichiediElencoArticoli, RichiediElencoMovimenti, RichiediElencoStock,
)
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.magazzino_lettura import (
    PostgreSQLMagazzinoLetturaReader,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)

# NOTA: raccolta_id/consegna_id/run_id sono LEFT JOIN strutturalmente identiche
# alle join varieta_id/articolo_id gia' coperte qui (stessa forma: id interno ->
# public_id via chiave esterna nullable). Questo fixture verifica il percorso
# "nessuna origine strutturata" (origine_tipo diverso da RACCOLTA/CONSEGNA,
# quindi raccolta_id/consegna_id NULL per vincolo DB
# ck_movimenti_magazzino_origine_references); l'associazione RACCOLTA->stock
# reale passa dal comando MOVIMENTO_CARICO_RACCOLTA (non testato qui: fuori
# dallo scope di sola lettura di questo boundary, la sua correttezza e' gia'
# verificata dai test della sua Application/infrastruttura dedicata).


@pytest.fixture
def magazzino_environment(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_magazzino_lettura_{uuid.uuid4().hex}"
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
            "INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at,version) "
            "SELECT id,100,'GRAM',%s,0 FROM tpo.varieta WHERE public_id='VAR-000001'",
            (NOW,),
        )
        connection.exec_driver_sql(
            "INSERT INTO tpo.articoli(public_id,denominazione,unita_misura,created_by) "
            "VALUES ('ART-000001','Vaschette 24 fori','UNIT','test')"
        )
        connection.exec_driver_sql(
            "INSERT INTO tpo.stock_articoli(articolo_id,disponibile,unita_misura,updated_at,"
            "version) SELECT id,50,'UNIT',%s,0 FROM tpo.articoli WHERE public_id='ART-000001'",
            (NOW,),
        )
        connection.exec_driver_sql(
            "INSERT INTO tpo.movimenti_magazzino(public_id,varieta_id,unita_misura,tipo,"
            "direzione,quantita,data_movimento,motivo,origine_tipo,created_by) "
            "SELECT 'MOV-000001',id,'GRAM','CARICO','POSITIVO',10,%s,'carico iniziale',"
            "'RETTIFICA_MANUALE','test' FROM tpo.varieta WHERE public_id='VAR-000001'",
            (NOW - timedelta(days=1),),
        )
        connection.exec_driver_sql(
            "INSERT INTO tpo.movimenti_magazzino(public_id,articolo_id,unita_misura,tipo,"
            "direzione,quantita,data_movimento,motivo,origine_tipo,created_by) "
            "SELECT 'MOV-000002',id,'UNIT','SCARICO','NEGATIVO',5,%s,'uso vaschette',"
            "'RETTIFICA_MANUALE','test' FROM tpo.articoli WHERE public_id='ART-000001'",
            (NOW,),
        )
    return engine


def test_articoli_are_read_ordered_by_denominazione(magazzino_environment):
    reader = PostgreSQLMagazzinoLetturaReader(_Factory(magazzino_environment))
    result = reader.articoli(RichiediElencoArticoli())
    assert [a.articolo_id.value for a in result.articoli] == ["ART-000001"]
    assert result.articoli[0].denominazione == "Vaschette 24 fori"
    assert result.articoli[0].unita_misura == "UNIT"


def test_stock_reads_both_varieta_and_articoli_rows(magazzino_environment):
    reader = PostgreSQLMagazzinoLetturaReader(_Factory(magazzino_environment))
    result = reader.stock(RichiediElencoStock())
    assert len(result.stock_varieta) == 1
    assert result.stock_varieta[0].varieta_id.value == "VAR-000001"
    assert result.stock_varieta[0].varieta_denominazione == "Rucola"
    assert result.stock_varieta[0].disponibile == Decimal("100")
    assert result.stock_varieta[0].unita_misura == "GRAM"
    assert len(result.stock_articoli) == 1
    assert result.stock_articoli[0].articolo_id.value == "ART-000001"
    assert result.stock_articoli[0].disponibile == Decimal("50")


def test_movimenti_ordered_by_data_movimento_descending_with_xor_resources(
    magazzino_environment,
):
    reader = PostgreSQLMagazzinoLetturaReader(_Factory(magazzino_environment))
    result = reader.movimenti(RichiediElencoMovimenti())
    ids = [m.movimento_id.value for m in result.movimenti]
    assert ids == ["MOV-000002", "MOV-000001"]
    per_varieta, per_articolo = result.movimenti[1], result.movimenti[0]
    assert per_varieta.varieta_id.value == "VAR-000001"
    assert per_varieta.varieta_denominazione == "Rucola"
    assert per_varieta.articolo_id is None
    assert per_varieta.articolo_denominazione is None
    assert per_varieta.tipo == "CARICO" and per_varieta.direzione == "POSITIVO"
    assert per_varieta.raccolta_id is None
    assert per_varieta.consegna_id is None
    assert per_varieta.run_id is None
    assert per_articolo.articolo_id.value == "ART-000001"
    assert per_articolo.articolo_denominazione == "Vaschette 24 fori"
    assert per_articolo.varieta_id is None
    assert per_articolo.tipo == "SCARICO" and per_articolo.direzione == "NEGATIVO"
    assert per_articolo.quantita == Decimal("5")


def test_elenco_empty_when_no_rows(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_magazzino_lettura_empty_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
    reader = PostgreSQLMagazzinoLetturaReader(_Factory(engine))
    assert reader.articoli(RichiediElencoArticoli()).articoli == ()
    stock = reader.stock(RichiediElencoStock())
    assert stock.stock_varieta == () and stock.stock_articoli == ()
    assert reader.movimenti(RichiediElencoMovimenti()).movimenti == ()
