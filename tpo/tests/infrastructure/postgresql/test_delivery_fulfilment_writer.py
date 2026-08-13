from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import threading
import time
import uuid
from zoneinfo import ZoneInfo

from alembic import command as alembic_command
import psycopg
import pytest
import sqlalchemy as sa

from src.tpo_core.application.delivery_fulfilment import (
    DeliveryAlreadyPublishedError,
    DeliveryFulfilmentCommand,
    DeliveryFulfilmentLine,
    DeliveryLineReference,
    DeliveryConcurrencyError,
    DeliveryValidationError,
)
from src.tpo_core.domain.identifiers import (
    ActorId, ClienteId, ConsegnaId, MovimentoId, OrdineId,
)
from src.tpo_core.domain.quantities import UnitOfMeasure
from src.tpo_core.domain.time_reference import CurrentSystemDate
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.delivery_fulfilment_writer import (
    PostgreSQLDeliveryFulfilmentWriter,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql as migration_postgresql,
)


TZ = ZoneInfo("Atlantic/Canary")
NOW = datetime(2099, 1, 1, 10, tzinfo=TZ)
PERSISTENCE_NOW = datetime(2099, 1, 2, 11, tzinfo=TZ)


class _FixedClock:
    def __init__(self, value: datetime = PERSISTENCE_NOW) -> None:
        self.value = CurrentSystemDate(value)

    def now(self) -> CurrentSystemDate:
        return self.value


@pytest.fixture(scope="module")
def writer_postgresql_cluster_engine(migration_postgresql):
    """Reuse only the disposable server; behavioral databases stay isolated."""
    return migration_postgresql.engine


@pytest.fixture
def writer_postgresql_engine(writer_postgresql_cluster_engine):
    """Create a migrated database dedicated to one commit-capable writer test."""
    admin_engine = writer_postgresql_cluster_engine
    database_name = f"tpo_writer_{uuid.uuid4().hex}"
    with admin_engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    engine = sa.create_engine(admin_engine.url.set(database=database_name))
    try:
        with engine.connect() as connection:
            alembic_command.upgrade(make_config(connection=connection), "head")
            connection.commit()
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT count(*) FROM tpo.consegne"
            ).scalar_one() == 0
            assert connection.exec_driver_sql(
                "SELECT count(*) FROM tpo.audit_eventi"
            ).scalar_one() == 0
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            connection.exec_driver_sql(
                f'DROP DATABASE "{database_name}" WITH (FORCE)'
            )


class _Factory:
    def __init__(self, engine, *, application_name: str | None = None) -> None:
        self.url = engine.url
        self.application_name = application_name

    def connect(self):
        parameters = dict(
            host=self.url.host, port=self.url.port, dbname=self.url.database,
            user=self.url.username, connect_timeout=5,
        )
        if self.application_name is not None:
            parameters["application_name"] = self.application_name
        return psycopg.connect(**parameters)


class _BlockingCursor:
    def __init__(self, cursor, *, acquired: threading.Event,
                 release: threading.Event) -> None:
        self._cursor = cursor
        self._acquired = acquired
        self._release = release

    def execute(self, query, params=None):
        result = self._cursor.execute(query, params)
        sql = " ".join(str(query).split())
        if "FROM tpo.ordini" in sql and "FOR UPDATE" in sql:
            self._acquired.set()
            assert self._release.wait(10)
        return result

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _BlockingConnection:
    def __init__(self, connection, *, acquired: threading.Event,
                 release: threading.Event) -> None:
        self._connection = connection
        self._acquired = acquired
        self._release = release

    def cursor(self):
        return _BlockingCursor(
            self._connection.cursor(), acquired=self._acquired, release=self._release
        )

    def __getattr__(self, name):
        return getattr(self._connection, name)


class _BlockingFactory(_Factory):
    def __init__(self, engine, acquired: threading.Event,
                 release: threading.Event) -> None:
        super().__init__(engine)
        self._acquired = acquired
        self._release = release

    def connect(self):
        return _BlockingConnection(
            super().connect(), acquired=self._acquired, release=self._release
        )


def _seed(engine, number: int, *, stock: str = "2", lines: int = 1,
          client_offset: int = 0) -> None:
    with engine.begin() as connection:
        client = connection.exec_driver_sql("""
          INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
          VALUES (%s,%s,'writer-test',%s,'writer-test') RETURNING id
        """, (f"CLI-{number + client_offset:06d}", f"Writer client {number}", NOW)).scalar_one()
        variety = connection.exec_driver_sql("""
          INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,updated_at,updated_by)
          VALUES (%s,%s,'ATTIVA','writer-test',%s,'writer-test') RETURNING id
        """, (f"VAR-{number:06d}", f"Writer variety {number}", NOW)).scalar_one()
        order = connection.exec_driver_sql("""
          INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,
                                 stato,tipo_creazione,created_by)
          VALUES (%s,%s,DATE '2099-01-01',DATE '2099-01-01','APERTO','MANUALE','writer-test')
          RETURNING id
        """, (f"ORD-{number:06d}", client)).scalar_one()
        for position in range(1, lines + 1):
            connection.exec_driver_sql("""
              INSERT INTO tpo.righe_ordine
                (ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
              VALUES (%s,%s,%s,1,'SET',%s)
            """, (order, position, variety, f"RO-{number + position - 1:06d}"))
        connection.exec_driver_sql("""
          INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at)
          VALUES (%s,%s,'SET',%s)
        """, (variety, stock, NOW))


def _command(number: int, quantity: str, *, order_version: int = 0,
             line_version: int = 0, correction_of: int | None = None,
             movement: int | None = None, line_number: int | None = None,
             client_number: int | None = None) -> DeliveryFulfilmentCommand:
    line_no = number if line_number is None else line_number
    reference = None if correction_of is None else DeliveryLineReference(
        ConsegnaId(f"CON-{correction_of:06d}"), 1
    )
    movement_id = None if movement is None else MovimentoId(f"MOV-{movement:06d}")
    line = DeliveryFulfilmentLine(
        OrdineId(f"ORD-{line_no:06d}"), f"RO-{line_no:06d}", Decimal(quantity),
        UnitOfMeasure.SET, order_version, line_version, movement_id, reference,
    )
    return DeliveryFulfilmentCommand(
        ConsegnaId(f"CON-{number:06d}"),
        ClienteId(f"CLI-{client_number if client_number is not None else line_no:06d}"),
        date(2099, 1, 1), NOW, (line,), ActorId("writer-test"),
        "writer integration test", f"writer-{number}",
    )


def _writer(
    engine, clock=None, *, application_name: str | None = None
) -> PostgreSQLDeliveryFulfilmentWriter:
    return PostgreSQLDeliveryFulfilmentWriter(
        _Factory(engine, application_name=application_name),
        _FixedClock() if clock is None else clock,
    )


def _facts(engine, number: int):
    with engine.connect() as connection:
        return connection.exec_driver_sql("""
          SELECT o.stato,o.version,ro.version,s.disponibile,s.version,
                 (SELECT count(*) FROM tpo.movimenti_magazzino m
                   WHERE m.origine_riferimento=%s),
                 (SELECT count(*) FROM tpo.audit_eventi a
                   WHERE a.correlation_id LIKE %s)
          FROM tpo.ordini o JOIN tpo.righe_ordine ro ON ro.ordine_id=o.id
          JOIN tpo.stock s ON s.varieta_id=ro.varieta_id
          WHERE o.public_id=%s
        """, (f"CON-{number:06d}", f"writer-{number}%", f"ORD-{number:06d}")).one()


def test_real_postgresql_partial_complete_and_commercial_correction(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 910001)
    writer = _writer(engine)
    partial = writer.publish(_command(910001, "0.5", movement=910001))
    assert partial.order_states[0][1] == "PARZIALMENTE_EVASO"
    assert partial.movement_count == 1
    assert _facts(engine, 910001) == (
        "PARZIALMENTE_EVASO", 1, 1, Decimal("1.500000"), 1, 1, 3,
    )
    with engine.connect() as connection:
        audits = connection.exec_driver_sql("""
          SELECT entity_type,entity_public_id,operation,actor,correlation_id,
                 before_data,after_data,occurred_at
          FROM tpo.audit_eventi WHERE correlation_id='writer-910001'
          ORDER BY id
        """).all()
    assert [(row[0], row[1], row[2]) for row in audits] == [
        ("RIGA_CONSEGNA", "CON-910001", "INSERT"),
        ("ORDINE", "ORD-910001", "STATE_TRANSITION"),
        ("CONSEGNA", "CON-910001", "INSERT"),
    ]
    assert all(row[3] == "writer-test" for row in audits)
    assert all(row[4] == "writer-910001" for row in audits)
    assert all(row[7] == PERSISTENCE_NOW for row in audits)
    assert audits[0][6]["position"] == 1
    assert audits[0][6]["movement_public_id"] == "MOV-910001"
    assert audits[1][5] == {
        "public_id": "ORD-910001", "state": "APERTO", "version": 0,
    }
    assert audits[1][6] == {
        "public_id": "ORD-910001", "state": "PARZIALMENTE_EVASO", "version": 1,
    }
    assert audits[2][6]["line_count"] == 1
    assert audits[2][6]["movement_count"] == 1

    complete = writer.publish(_command(
        910002, "0.5", order_version=1, line_version=1, movement=910002,
        line_number=910001, client_number=910001,
    ))
    assert complete.order_states[0][1] == "EVASO"
    correction = writer.publish(_command(
        910003, "-0.25", order_version=2, line_version=2,
        correction_of=910001, line_number=910001, client_number=910001,
    ))
    assert correction.order_states[0][1] == "PARZIALMENTE_EVASO"
    with engine.connect() as connection:
        row = connection.exec_driver_sql("""
          SELECT o.stato,o.version,ro.version,s.disponibile,s.version,
                 count(m.id) FILTER (WHERE m.origine_tipo='CONSEGNA')
          FROM tpo.ordini o JOIN tpo.righe_ordine ro ON ro.ordine_id=o.id
          JOIN tpo.stock s ON s.varieta_id=ro.varieta_id
          LEFT JOIN tpo.movimenti_magazzino m ON m.varieta_id=s.varieta_id
          WHERE o.public_id='ORD-910001'
          GROUP BY o.stato,o.version,ro.version,s.disponibile,s.version
        """).one()
    assert row == ("PARZIALMENTE_EVASO", 3, 3, Decimal("1.000000"), 2, 2)


def test_real_postgresql_overdelivery_rolls_back_everything(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 920001)
    with pytest.raises(DeliveryValidationError):
        _writer(engine).publish(_command(920001, "1.1", movement=920001))
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.consegne WHERE public_id='CON-920001'"
        ).scalar_one() == 0
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE correlation_id='writer-920001'"
        ).scalar_one() == 0
    assert _facts(engine, 920001)[:5] == ("APERTO", 0, 0, Decimal("2.000000"), 0)


def test_real_postgresql_separates_business_and_persistence_timestamps(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 925001)
    _writer(engine, _FixedClock(PERSISTENCE_NOW)).publish(
        _command(925001, "0.5", movement=925001)
    )
    with engine.connect() as connection:
        timestamps = connection.exec_driver_sql("""
          SELECT c.data_effettiva,c.created_at,rc.created_at,
                 m.data_movimento,m.created_at,s.updated_at,
                 min(a.occurred_at),max(a.occurred_at)
          FROM tpo.consegne c
          JOIN tpo.righe_consegna rc ON rc.consegna_id=c.id
          JOIN tpo.movimenti_magazzino m ON m.riga_consegna_id=rc.id
          JOIN tpo.stock s ON s.varieta_id=rc.varieta_id
          JOIN tpo.audit_eventi a ON a.correlation_id='writer-925001'
          WHERE c.public_id='CON-925001'
          GROUP BY c.data_effettiva,c.created_at,rc.created_at,
                   m.data_movimento,m.created_at,s.updated_at
        """).one()
    assert timestamps[0] == NOW
    assert timestamps[3] == NOW
    assert timestamps[1:] == (
        PERSISTENCE_NOW, PERSISTENCE_NOW, NOW, PERSISTENCE_NOW,
        PERSISTENCE_NOW, PERSISTENCE_NOW, PERSISTENCE_NOW,
    )


def test_real_postgresql_insufficient_stock_rolls_back_commercial_facts(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 930001, stock="0.25")
    with pytest.raises(DeliveryValidationError, match="STOCK insufficiente"):
        _writer(engine).publish(_command(930001, "0.5", movement=930001))
    assert _facts(engine, 930001)[:5] == ("APERTO", 0, 0, Decimal("0.250000"), 0)


def test_real_postgresql_duplicate_delivery_is_the_idempotency_boundary(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 940001)
    command = _command(940001, "0.5", movement=940001)
    _writer(engine).publish(command)
    with pytest.raises(DeliveryAlreadyPublishedError):
        _writer(engine).publish(command)


def test_real_postgresql_correction_to_zero_and_positive_correction_do_not_touch_stock(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 950001)
    writer = _writer(engine)
    writer.publish(_command(950001, "0.5", movement=950001))
    reopened = writer.publish(_command(
        950002, "-0.5", order_version=1, line_version=1,
        correction_of=950001, line_number=950001, client_number=950001,
    ))
    assert reopened.order_states[0][1] == "APERTO"
    assert _facts(engine, 950001)[:5] == (
        "APERTO", 2, 2, Decimal("1.500000"), 1,
    )
    increased = writer.publish(_command(
        950003, "0.25", order_version=2, line_version=2,
        correction_of=950001, line_number=950001, client_number=950001,
    ))
    assert increased.order_states[0][1] == "PARZIALMENTE_EVASO"
    assert _facts(engine, 950001)[:5] == (
        "PARZIALMENTE_EVASO", 3, 3, Decimal("1.500000"), 1,
    )


def test_real_postgresql_rejects_correction_of_correction(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 960001)
    writer = _writer(engine)
    writer.publish(_command(960001, "0.5", movement=960001))
    writer.publish(_command(
        960002, "-0.25", order_version=1, line_version=1,
        correction_of=960001, line_number=960001, client_number=960001,
    ))
    with pytest.raises(DeliveryValidationError, match="riga ordinaria"):
        writer.publish(_command(
            960003, "-0.1", order_version=2, line_version=2,
            correction_of=960002, line_number=960001, client_number=960001,
        ))
    assert _facts(engine, 960001)[:5] == (
        "PARZIALMENTE_EVASO", 2, 2, Decimal("1.500000"), 1,
    )


def test_real_postgresql_rejects_wrong_uom_client_and_cancelled_order(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 970001)
    writer = _writer(engine)
    wrong_uom = DeliveryFulfilmentCommand(
        ConsegnaId("CON-970001"), ClienteId("CLI-970001"), date(2099, 1, 1),
        NOW, (DeliveryFulfilmentLine(
            OrdineId("ORD-970001"), "RO-970001", Decimal("0.5"),
            UnitOfMeasure.GRAM, 0, 0, MovimentoId("MOV-970001"),
        ),), ActorId("writer-test"), "wrong uom", "writer-970001",
    )
    with pytest.raises(DeliveryValidationError, match="UOM"):
        writer.publish(wrong_uom)
    with engine.begin() as connection:
        connection.exec_driver_sql("""
          INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
          VALUES ('CLI-970002','Other writer client','writer-test',%s,'writer-test')
        """, (NOW,))
    with pytest.raises(DeliveryValidationError, match="CLIENTE"):
        writer.publish(_command(
            970002, "0.5", movement=970002, line_number=970001,
            client_number=970002,
        ))
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE tpo.ordini SET stato='ANNULLATO' WHERE public_id='ORD-970001'"
        )
    with pytest.raises(DeliveryValidationError, match="ANNULLATO"):
        writer.publish(_command(
            970003, "0.5", movement=970003, line_number=970001,
            client_number=970001,
        ))


def test_real_postgresql_multi_line_increments_order_once_and_links_movements(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 980001, stock="3", lines=2)
    lines = (
        DeliveryFulfilmentLine(
            OrdineId("ORD-980001"), "RO-980001", Decimal("1"),
            UnitOfMeasure.SET, 0, 0, MovimentoId("MOV-980001"),
        ),
        DeliveryFulfilmentLine(
            OrdineId("ORD-980001"), "RO-980002", Decimal("0.5"),
            UnitOfMeasure.SET, 0, 0, MovimentoId("MOV-980002"),
        ),
    )
    command = DeliveryFulfilmentCommand(
        ConsegnaId("CON-980001"), ClienteId("CLI-980001"), date(2099, 1, 1),
        NOW, lines, ActorId("writer-test"), "multi-line", "writer-980001",
    )
    result = _writer(engine).publish(command)
    assert result.order_states == ((OrdineId("ORD-980001"), "PARZIALMENTE_EVASO"),)
    assert result.movement_count == 2
    with engine.connect() as connection:
        order_version = connection.exec_driver_sql(
            "SELECT version FROM tpo.ordini WHERE public_id='ORD-980001'"
        ).scalar_one()
        line_versions = connection.exec_driver_sql("""
          SELECT array_agg(version ORDER BY posizione) FROM tpo.righe_ordine
          WHERE ordine_id=(SELECT id FROM tpo.ordini WHERE public_id='ORD-980001')
        """).scalar_one()
        links = connection.exec_driver_sql("""
          SELECT count(*) FROM tpo.movimenti_magazzino m
          JOIN tpo.righe_consegna rc
            ON (rc.id,rc.consegna_id)=(m.riga_consegna_id,m.consegna_id)
          JOIN tpo.consegne c ON c.id=m.consegna_id
          WHERE c.public_id='CON-980001' AND m.tipo='SCARICO'
            AND m.direzione='NEGATIVO' AND m.origine_tipo='CONSEGNA'
        """).scalar_one()
    assert order_version == 1
    assert line_versions == [1, 1]
    assert links == 2


def test_real_postgresql_same_order_concurrency_is_serialized_then_conflicts(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 990001)
    acquired = threading.Event()
    release = threading.Event()
    second_started = threading.Event()
    outcomes: list[object] = []

    def first() -> None:
        try:
            outcomes.append(PostgreSQLDeliveryFulfilmentWriter(
                _BlockingFactory(engine, acquired, release), _FixedClock()
            ).publish(_command(990001, "0.5", movement=990001)))
        except Exception as exc:  # captured and asserted in the parent test
            outcomes.append(exc)

    def second() -> None:
        second_started.set()
        try:
            outcomes.append(_writer(
                engine, application_name="tpo-writer-contender"
            ).publish(_command(
                    990002, "0.6", movement=990002, line_number=990001,
                    client_number=990001,
                )))
        except Exception as exc:  # captured and asserted in the parent test
            outcomes.append(exc)

    thread_one = threading.Thread(target=first)
    thread_two = threading.Thread(target=second)
    thread_one.start()
    assert acquired.wait(10)
    thread_two.start()
    assert second_started.wait(10)
    deadline = time.monotonic() + 10
    contender_waiting = False
    while time.monotonic() < deadline:
        with engine.connect() as observer:
            contender_waiting = bool(observer.exec_driver_sql("""
              SELECT EXISTS (
                SELECT 1 FROM pg_stat_activity
                WHERE application_name='tpo-writer-contender'
                  AND wait_event_type='Lock'
              )
            """).scalar_one())
        if contender_waiting:
            break
        time.sleep(0.01)
    assert contender_waiting, "T2 never reached a PostgreSQL lock wait"
    release.set()
    thread_one.join(10)
    thread_two.join(10)
    assert not thread_one.is_alive() and not thread_two.is_alive()
    assert len(outcomes) == 2
    assert sum(isinstance(item, DeliveryConcurrencyError) for item in outcomes) == 1
    assert _facts(engine, 990001)[:5] == (
        "PARZIALMENTE_EVASO", 1, 1, Decimal("1.500000"), 1,
    )
