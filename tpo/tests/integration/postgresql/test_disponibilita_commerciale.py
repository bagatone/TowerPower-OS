from datetime import datetime, timezone
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.disponibilita_commerciale.errors import (
    DisponibilitaCommercialeVarietaNotFoundError,
)
from src.tpo_core.application.disponibilita_commerciale.models import (
    RichiediDisponibilitaCommerciale,
)
from src.tpo_core.domain.identifiers import VarietaId
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.disponibilita_commerciale import (
    PostgreSQLDisponibilitaCommercialeReader,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def disponibilita_environment(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_disponibilita_{uuid.uuid4().hex}"
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
            "INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by) "
            "VALUES ('CLI-000001','Cliente test','test',%s,'test')", (NOW,),
        )
    return engine


def _varieta_pk(engine) -> int:
    with engine.connect() as connection:
        return connection.exec_driver_sql(
            "SELECT id FROM tpo.varieta WHERE public_id='VAR-000001'"
        ).scalar_one()


def _cliente_pk(engine) -> int:
    with engine.connect() as connection:
        return connection.exec_driver_sql(
            "SELECT id FROM tpo.clienti WHERE public_id='CLI-000001'"
        ).scalar_one()


def _ordine(engine, *, public_id: str, stato: str, righe: list[tuple[str, float]]) -> int:
    varieta_pk = _varieta_pk(engine)
    cliente_pk = _cliente_pk(engine)
    with engine.begin() as connection:
        ordine_pk = connection.exec_driver_sql(
            """INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,
                                       stato,tipo_creazione,created_by)
               VALUES (%s,%s,DATE '2099-01-01',DATE '2099-01-01',%s,'MANUALE','test')
               RETURNING id""",
            (public_id, cliente_pk, stato),
        ).scalar_one()
        for index, (riga_public_id, quantita) in enumerate(righe, start=1):
            connection.exec_driver_sql(
                """INSERT INTO tpo.righe_ordine
                   (ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
                   VALUES (%s,%s,%s,%s,'GRAM',%s)""",
                (ordine_pk, index, varieta_pk, quantita, riga_public_id),
            )
    return ordine_pk


def _consegna(engine, *, ordine_pk: int) -> int:
    # stato='CONSEGNATA' (con data_effettiva valorizzata, ck_consegne_data_effettiva)
    # perche' il calcolo PRENOTATO conta come "consegnato" solo le righe_consegna
    # collegate a una CONSEGNA effettivamente CONSEGNATA (stessa definizione di
    # "delivered" usata da fn_check_fulfilment_bounds/fn_check_ordine_fulfilment_state
    # per i trigger di coerenza su tpo.ordini/tpo.righe_consegna).
    with engine.begin() as connection:
        consegna_pk = connection.exec_driver_sql(
            """INSERT INTO tpo.consegne(public_id,cliente_id,stato,data_prevista,
                                         data_effettiva,created_by)
               VALUES (%s,%s,'CONSEGNATA',DATE '2099-01-01',%s,'test') RETURNING id""",
            (f"CON-{ordine_pk:06d}", _cliente_pk(engine), NOW),
        ).scalar_one()
        connection.exec_driver_sql(
            """INSERT INTO tpo.consegne_ordini(consegna_id,ordine_id,posizione)
               VALUES (%s,%s,1)""",
            (consegna_pk, ordine_pk),
        )
    return consegna_pk


def _consegna_riga(engine, *, consegna_pk: int, ordine_pk: int, riga_pk: int,
                    quantita: float, posizione: int = 1) -> None:
    varieta_pk = _varieta_pk(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """INSERT INTO tpo.righe_consegna
               (consegna_id,ordine_id,riga_ordine_id,posizione,varieta_id,quantita,
                unita_misura,created_at,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,'GRAM',%s,'test')""",
            (consegna_pk, ordine_pk, riga_pk, posizione, varieta_pk, quantita, NOW),
        )


def _riga_ordine_pk(engine, public_id: str) -> int:
    with engine.connect() as connection:
        return connection.exec_driver_sql(
            "SELECT id FROM tpo.righe_ordine WHERE public_id=%s", (public_id,),
        ).scalar_one()


def test_prenotato_is_zero_with_no_orders(disponibilita_environment):
    engine = disponibilita_environment
    reader = PostgreSQLDisponibilitaCommercialeReader(_Factory(engine))
    result = reader.disponibilita(
        RichiediDisponibilitaCommerciale(VarietaId("VAR-000001"))
    )
    assert result.disponibile == 0
    assert result.prenotato == 0
    assert result.vendibile == 0
    assert result.integrita_allarme is False


def test_prenotato_counts_open_order_lines(disponibilita_environment):
    engine = disponibilita_environment
    _ordine(engine, public_id="ORD-000001", stato="APERTO",
            righe=[("RO-000001", 100)])
    reader = PostgreSQLDisponibilitaCommercialeReader(_Factory(engine))
    result = reader.disponibilita(
        RichiediDisponibilitaCommerciale(VarietaId("VAR-000001"))
    )
    assert result.prenotato == 100


def test_prenotato_ignores_evaso_and_annullato_orders(disponibilita_environment):
    engine = disponibilita_environment
    _ordine(engine, public_id="ORD-000002", stato="EVASO", righe=[("RO-000002", 50)])
    _ordine(engine, public_id="ORD-000003", stato="ANNULLATO", righe=[("RO-000003", 70)])
    reader = PostgreSQLDisponibilitaCommercialeReader(_Factory(engine))
    result = reader.disponibilita(
        RichiediDisponibilitaCommerciale(VarietaId("VAR-000001"))
    )
    assert result.prenotato == 0


def test_prenotato_subtracts_delivered_quantity(disponibilita_environment):
    engine = disponibilita_environment
    ordine_pk = _ordine(engine, public_id="ORD-000004", stato="PARZIALMENTE_EVASO",
                         righe=[("RO-000004", 100)])
    consegna_pk = _consegna(engine, ordine_pk=ordine_pk)
    riga_pk = _riga_ordine_pk(engine, "RO-000004")
    _consegna_riga(engine, consegna_pk=consegna_pk, ordine_pk=ordine_pk, riga_pk=riga_pk,
                   quantita=30)
    reader = PostgreSQLDisponibilitaCommercialeReader(_Factory(engine))
    result = reader.disponibilita(
        RichiediDisponibilitaCommerciale(VarietaId("VAR-000001"))
    )
    assert result.prenotato == 70


def test_prenotato_floors_at_zero_when_fully_delivered(disponibilita_environment):
    engine = disponibilita_environment
    # stato='EVASO', non 'PARZIALMENTE_EVASO': la riga viene consegnata per intero
    # (20 su 20) qui sotto, e ct_ordini_fulfilment_state (fn_check_ordine_fulfilment_state,
    # verificato in modo deferred all'INSERT su righe_consegna) si aspetta EVASO quando
    # delivered==ordered per tutte le righe -- coerente con la regola di dominio "un
    # ordine evaso non prenota più nulla" già verificata altrove in questo file.
    ordine_pk = _ordine(engine, public_id="ORD-000005", stato="EVASO",
                         righe=[("RO-000005", 20)])
    consegna_pk = _consegna(engine, ordine_pk=ordine_pk)
    riga_pk = _riga_ordine_pk(engine, "RO-000005")
    _consegna_riga(engine, consegna_pk=consegna_pk, ordine_pk=ordine_pk, riga_pk=riga_pk,
                   quantita=20)
    reader = PostgreSQLDisponibilitaCommercialeReader(_Factory(engine))
    result = reader.disponibilita(
        RichiediDisponibilitaCommerciale(VarietaId("VAR-000001"))
    )
    assert result.prenotato == 0


def test_vendibile_negative_raises_integrity_alarm_without_writing_stock(disponibilita_environment):
    engine = disponibilita_environment
    with engine.begin() as connection:
        varieta_pk = _varieta_pk(engine)
        connection.exec_driver_sql(
            "INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at,version) "
            "VALUES (%s,50,'GRAM',%s,0)", (varieta_pk, NOW),
        )
    _ordine(engine, public_id="ORD-000006", stato="APERTO", righe=[("RO-000006", 90)])
    reader = PostgreSQLDisponibilitaCommercialeReader(_Factory(engine))
    result = reader.disponibilita(
        RichiediDisponibilitaCommerciale(VarietaId("VAR-000001"))
    )
    assert result.disponibile == 50
    assert result.prenotato == 90
    assert result.vendibile == -40
    assert result.integrita_allarme is True
    with engine.connect() as connection:
        stock_disponibile = connection.exec_driver_sql(
            "SELECT disponibile FROM tpo.stock WHERE varieta_id=%s", (varieta_pk,),
        ).scalar_one()
    assert stock_disponibile == 50


def test_rejects_unknown_varieta(disponibilita_environment):
    engine = disponibilita_environment
    reader = PostgreSQLDisponibilitaCommercialeReader(_Factory(engine))
    with pytest.raises(DisponibilitaCommercialeVarietaNotFoundError):
        reader.disponibilita(RichiediDisponibilitaCommerciale(VarietaId("VAR-999999")))
