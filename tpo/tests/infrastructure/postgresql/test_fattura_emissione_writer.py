from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid
from zoneinfo import ZoneInfo

from alembic import command as alembic_command
import psycopg
import pytest
import sqlalchemy as sa

from src.tpo_core.application.delivery_fulfilment.models import (
    DeliveryFulfilmentCommand, DeliveryFulfilmentLine,
)
from src.tpo_core.application.fattura_emissione import (
    EmitFattura,
    EmitFatturaAuthority,
    FatturaIdempotencyConflictError,
    FatturaValidationError,
)
from src.tpo_core.domain.identifiers import ActorId, ClienteId, ConsegnaId, MovimentoId, OrdineId
from src.tpo_core.domain.quantities import UnitOfMeasure
from src.tpo_core.domain.time_reference import CurrentSystemDate
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.delivery_fulfilment_writer import (
    PostgreSQLDeliveryFulfilmentWriter,
)
from src.tpo_core.infrastructure.postgresql.fattura_emissione import (
    PostgreSQLFatturaEmissioneWriter,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql as migration_postgresql,
)

TZ = ZoneInfo("Atlantic/Canary")
NOW = datetime(2099, 1, 1, 10, tzinfo=TZ)


class _FixedClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = CurrentSystemDate(value)

    def now(self) -> CurrentSystemDate:
        return self.value


@pytest.fixture(scope="module")
def fattura_postgresql_cluster_engine(migration_postgresql):
    return migration_postgresql.engine


@pytest.fixture
def fattura_postgresql_engine(fattura_postgresql_cluster_engine):
    admin_engine = fattura_postgresql_cluster_engine
    database_name = f"tpo_fattura_{uuid.uuid4().hex}"
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    engine = sa.create_engine(admin_engine.url.set(database=database_name))
    try:
        with engine.connect() as connection:
            alembic_command.upgrade(make_config(connection=connection), "head")
            connection.commit()
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')


class _Factory:
    def __init__(self, engine) -> None:
        self.url = engine.url

    def connect(self):
        return psycopg.connect(
            host=self.url.host, port=self.url.port, dbname=self.url.database,
            user=self.url.username, connect_timeout=5,
        )


def _writer(engine) -> PostgreSQLFatturaEmissioneWriter:
    return PostgreSQLFatturaEmissioneWriter(_Factory(engine))


def _seed(engine, number: int, *, termini_pagamento_giorni: int | None = 30,
          prezzo_unitario: str = "5.0000", aliquota_igic: str = "7.00",
          consegne: int = 1, quantity: str = "2", listino: bool = True) -> None:
    """Crea CLIENTE/VARIETA/LISTINO_VARIETA e poi CONSEGNE realmente evase tramite
    il writer Delivery Fulfilment già congelato, cosi' tutti i trigger di coerenza
    ordine/consegna/stock esistenti restano rispettati invece di essere aggirati
    con INSERT manuali."""
    with engine.begin() as connection:
        cliente_id = connection.exec_driver_sql("""
          INSERT INTO tpo.clienti
            (public_id,denominazione,modalita_fatturazione,termini_pagamento_giorni,
             created_by,updated_at,updated_by)
          VALUES (%s,%s,'A_CONSEGNA',%s,'fattura-writer-test',%s,'fattura-writer-test')
          RETURNING id
        """, (f"CLI-{number:06d}", f"Fattura client {number}", termini_pagamento_giorni, NOW)).scalar_one()
        varieta_id = connection.exec_driver_sql("""
          INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,updated_at,updated_by)
          VALUES (%s,%s,'ATTIVA','fattura-writer-test',%s,'fattura-writer-test') RETURNING id
        """, (f"VAR-{number:06d}", f"Fattura variety {number}", NOW)).scalar_one()
        if listino:
            connection.exec_driver_sql("""
              INSERT INTO tpo.listino_varieta
                (varieta_id,prezzo_unitario,aliquota_igic,created_at,created_by,updated_at,updated_by)
              VALUES (%s,%s,%s,%s,'fattura-writer-test',%s,'fattura-writer-test')
            """, (varieta_id, prezzo_unitario, aliquota_igic, NOW, NOW))
        connection.exec_driver_sql("""
          INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at)
          VALUES (%s,%s,'GRAM',%s)
        """, (varieta_id, str(Decimal(quantity) * consegne + Decimal("1000")), NOW))
        for offset in range(consegne):
            order_no = number + offset
            order_id = connection.exec_driver_sql("""
              INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,
                                     stato,tipo_creazione,created_by)
              VALUES (%s,%s,DATE '2099-01-01',DATE '2099-01-01','APERTO','MANUALE','fattura-writer-test')
              RETURNING id
            """, (f"ORD-{order_no:06d}", cliente_id)).scalar_one()
            connection.exec_driver_sql("""
              INSERT INTO tpo.righe_ordine(ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
              VALUES (%s,1,%s,%s,'GRAM',%s)
            """, (order_id, varieta_id, quantity, f"RO-{order_no:06d}"))

    delivery_writer = PostgreSQLDeliveryFulfilmentWriter(_Factory(engine), _FixedClock())
    for offset in range(consegne):
        order_no = number + offset
        line = DeliveryFulfilmentLine(
            OrdineId(f"ORD-{order_no:06d}"), f"RO-{order_no:06d}", Decimal(quantity),
            UnitOfMeasure.GRAM, 0, 0, MovimentoId(f"MOV-{order_no:06d}"),
        )
        delivery_writer.publish(DeliveryFulfilmentCommand(
            ConsegnaId(f"CON-{order_no:06d}"), ClienteId(f"CLI-{number:06d}"),
            date(2099, 1, 1), NOW, (line,), ActorId("fattura-writer-test"),
            "fattura seed", f"fattura-seed-{order_no}",
        ))


def _command(number: int, *, consegne: int = 1, data_emissione: date = date(2026, 9, 3),
             idempotency_key: str | None = None) -> EmitFattura:
    return EmitFattura(
        cliente_id=ClienteId(f"CLI-{number:06d}"),
        consegna_ids=tuple(
            ConsegnaId(f"CON-{number + offset:06d}") for offset in range(consegne)
        ),
        data_emissione=data_emissione,
        authority=EmitFatturaAuthority(
            ActorId("fattura-writer-test"), "writer integration test", f"fattura-{number}",
            idempotency_key or f"fattura-key-{number}",
        ),
    )


def test_real_postgresql_emits_fattura_with_correct_totals_and_numbering(fattura_postgresql_engine) -> None:
    engine = fattura_postgresql_engine
    _seed(engine, 930001, consegne=2)
    writer = _writer(engine)
    result = writer.emit(_command(930001, consegne=2))
    assert result.outcome == "INSERTED"
    assert result.numero_fattura.value == "2026/0001"
    assert result.scadenza == date(2026, 10, 3)
    assert result.totale_netto == Decimal("20.00")
    assert result.totale_igic == Decimal("1.40")
    assert result.totale == Decimal("21.40")
    assert result.consegna_count == 2
    assert result.riga_count == 2
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.fatture_consegne WHERE fattura_id=%s", (result.fattura_id,)
        ).scalar_one() == 2
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.righe_fattura WHERE fattura_id=%s", (result.fattura_id,)
        ).scalar_one() == 2
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='FATTURA' AND entity_public_id=%s",
            (result.numero_fattura.value,),
        ).scalar_one() == 1


def test_real_postgresql_numbering_is_sequential_within_year_and_resets_across_years(
    fattura_postgresql_engine,
) -> None:
    engine = fattura_postgresql_engine
    _seed(engine, 930101)
    _seed(engine, 930102)
    _seed(engine, 930103)
    writer = _writer(engine)
    first = writer.emit(_command(930101, data_emissione=date(2026, 1, 15)))
    second = writer.emit(_command(930102, data_emissione=date(2026, 12, 31)))
    third = writer.emit(_command(930103, data_emissione=date(2027, 1, 1)))
    assert first.numero_fattura.value == "2026/0001"
    assert second.numero_fattura.value == "2026/0002"
    assert third.numero_fattura.value == "2027/0001"


def test_real_postgresql_idempotent_replay_returns_same_numero_without_reallocating(
    fattura_postgresql_engine,
) -> None:
    engine = fattura_postgresql_engine
    _seed(engine, 930201)
    _seed(engine, 930202)
    writer = _writer(engine)
    first = writer.emit(_command(930201, idempotency_key="shared-key"))
    replay = writer.emit(_command(930201, idempotency_key="shared-key"))
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert replay.numero_fattura == first.numero_fattura
    second = writer.emit(_command(930202))
    assert second.numero_fattura.value == "2026/0002"


def test_real_postgresql_rejects_idempotency_key_reused_with_different_payload(
    fattura_postgresql_engine,
) -> None:
    engine = fattura_postgresql_engine
    _seed(engine, 930301, consegne=2)
    writer = _writer(engine)
    writer.emit(_command(930301, idempotency_key="conflict-key"))
    conflicting = EmitFattura(
        cliente_id=ClienteId("CLI-930301"),
        consegna_ids=(ConsegnaId("CON-930302"),),
        data_emissione=date(2026, 9, 3),
        authority=EmitFatturaAuthority(
            ActorId("fattura-writer-test"), "writer integration test", "fattura-930301b",
            "conflict-key",
        ),
    )
    with pytest.raises(FatturaIdempotencyConflictError):
        writer.emit(conflicting)


def test_real_postgresql_rejects_consegna_not_consegnata(fattura_postgresql_engine) -> None:
    # tr_consegne_effective_immutable impedisce di riportare indietro una CONSEGNA
    # gia' CONSEGNATA (e nessun writer esistente produce altri stati), percio' lo
    # stato non-CONSEGNATA viene creato qui direttamente in INSERT: i trigger
    # ct_consegne_order_state/ct_consegne_fulfilment_bounds scattano solo su
    # "AFTER UPDATE OF stato", non sull'INSERT iniziale.
    engine = fattura_postgresql_engine
    with engine.begin() as connection:
        cliente_id = connection.exec_driver_sql("""
          INSERT INTO tpo.clienti
            (public_id,denominazione,modalita_fatturazione,termini_pagamento_giorni,
             created_by,updated_at,updated_by)
          VALUES ('CLI-930401','Fattura client 930401','A_CONSEGNA',30,
                  'fattura-writer-test',%s,'fattura-writer-test')
          RETURNING id
        """, (NOW,)).scalar_one()
        connection.exec_driver_sql("""
          INSERT INTO tpo.consegne
            (public_id,cliente_id,stato,data_prevista,created_at,created_by)
          VALUES ('CON-930401',%s,'ANNULLATA',DATE '2099-01-01',%s,'fattura-writer-test')
        """, (cliente_id, NOW))
    writer = _writer(engine)
    with pytest.raises(FatturaValidationError):
        writer.emit(_command(930401))


def test_real_postgresql_rejects_consegna_already_invoiced(fattura_postgresql_engine) -> None:
    engine = fattura_postgresql_engine
    _seed(engine, 930501)
    writer = _writer(engine)
    writer.emit(_command(930501))
    with pytest.raises(FatturaValidationError):
        writer.emit(_command(930501, idempotency_key="second-attempt"))


def test_real_postgresql_rejects_missing_listino_varieta(fattura_postgresql_engine) -> None:
    engine = fattura_postgresql_engine
    _seed(engine, 930601, listino=False)
    writer = _writer(engine)
    with pytest.raises(FatturaValidationError):
        writer.emit(_command(930601))


def test_real_postgresql_rejects_cliente_without_termini_pagamento(fattura_postgresql_engine) -> None:
    engine = fattura_postgresql_engine
    _seed(engine, 930701, termini_pagamento_giorni=None)
    writer = _writer(engine)
    with pytest.raises(FatturaValidationError):
        writer.emit(_command(930701))


def test_real_postgresql_immutability_triggers_block_update_and_delete(fattura_postgresql_engine) -> None:
    engine = fattura_postgresql_engine
    _seed(engine, 930801)
    writer = _writer(engine)
    result = writer.emit(_command(930801))
    with engine.connect() as connection:
        with pytest.raises(Exception, match="tr_fatture_immutable violated"):
            connection.exec_driver_sql(
                "UPDATE tpo.fatture SET totale=totale+1 WHERE id=%s", (result.fattura_id,)
            )
        connection.rollback()
        with pytest.raises(Exception, match="tr_fatture_immutable violated"):
            connection.exec_driver_sql("DELETE FROM tpo.fatture WHERE id=%s", (result.fattura_id,))
        connection.rollback()
        with pytest.raises(Exception, match="tr_righe_fattura_immutable violated"):
            connection.exec_driver_sql(
                "UPDATE tpo.righe_fattura SET quantita=quantita+1 WHERE fattura_id=%s",
                (result.fattura_id,),
            )
        connection.rollback()
