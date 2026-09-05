from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.movimento_carico.errors import (
    MovimentoCaricoIdempotencyConflictError,
    MovimentoCaricoRaccoltaNotFoundError,
    MovimentoCaricoStockUnitMismatchError,
)
from src.tpo_core.application.movimento_carico.models import (
    MovimentoCaricoAuthority, RegistraCaricoMagazzino,
)
from src.tpo_core.domain.identifiers import ActorId, RaccoltaId
from src.tpo_core.infrastructure.postgresql.movimento_carico import (
    PostgreSQLMovimentoCaricoWriter,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)
from tests.integration.postgresql.test_raccolta import harvest, harvest_environment, ready
from tests.integration.postgresql.test_semina_commissioning import environment

BASE = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)


def carico(*, raccolta="RAC-000001", quantita="450.5", key="carico-1", at=BASE,
           motivo="pesatura carico"):
    return RegistraCaricoMagazzino(
        raccolta_id=RaccoltaId(raccolta),
        quantita_pesata=Decimal(quantita),
        effective_at=at,
        motivo=motivo,
        authority=MovimentoCaricoAuthority(
            ActorId("magazziniere"), "peso reale", f"corr-{key}", key,
        ),
    )


@pytest.fixture
def seeded_raccolta(harvest_environment):
    engine, raccolta_writer = harvest_environment
    ready(engine)
    result = raccolta_writer.record(harvest())
    # _seed_authorities (production_planning_commit_writer, riusata dalla catena
    # environment -> harvest_environment) pre-semina una riga tpo.stock legacy
    # per VAR-000001 in SET (baseline per i test di production planning, non
    # correlata a questo boundary). Il modello fisico di questo boundary parte
    # da nessuno stock esistente o da uno stock gia' in GRAM (Owner Decision
    # D11): la ripuliamo qui per isolare i test CARICO da quel fixture legacy.
    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM tpo.stock")
    return engine, result


def test_registra_carico_creates_movimento_and_increases_stock(seeded_raccolta):
    engine, raccolta = seeded_raccolta
    writer = PostgreSQLMovimentoCaricoWriter(_Factory(engine))
    result = writer.registra(carico(raccolta=raccolta.raccolta_id.value))
    assert result.outcome == "INSERTED"
    assert result.stock_disponibile == Decimal("450.5")
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT tipo,direzione,quantita,unita_misura,origine_tipo,raccolta_id "
            "FROM tpo.movimenti_magazzino WHERE public_id=%s",
            (result.movimento_id.value,),
        ).fetchone()
        assert row[0] == "CARICO"
        assert row[1] == "POSITIVO"
        assert Decimal(row[2]) == Decimal("450.5")
        assert row[3] == "GRAM"
        assert row[4] == "RACCOLTA"
        assert row[5] is not None
        stock_row = connection.exec_driver_sql(
            "SELECT disponibile,unita_misura FROM tpo.stock WHERE varieta_id="
            "(SELECT id FROM tpo.varieta WHERE public_id='VAR-000001')"
        ).fetchone()
        assert stock_row[0] == Decimal("450.5")
        assert stock_row[1] == "GRAM"
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='MOVIMENTO_MAGAZZINO' "
            "AND entity_public_id=%s AND operation='INSERT'",
            (result.movimento_id.value,),
        ).scalar_one() == 1


def test_multiple_partial_carichi_accumulate_stock(seeded_raccolta):
    engine, raccolta = seeded_raccolta
    writer = PostgreSQLMovimentoCaricoWriter(_Factory(engine))
    first = writer.registra(
        carico(raccolta=raccolta.raccolta_id.value, quantita="200", key="k1"),
    )
    second = writer.registra(
        carico(raccolta=raccolta.raccolta_id.value, quantita="150.25", key="k2"),
    )
    assert first.movimento_id != second.movimento_id
    assert second.stock_disponibile == Decimal("350.25")


def test_idempotent_replay_returns_same_movimento_without_double_counting(seeded_raccolta):
    engine, raccolta = seeded_raccolta
    writer = PostgreSQLMovimentoCaricoWriter(_Factory(engine))
    first = writer.registra(
        carico(raccolta=raccolta.raccolta_id.value, key="shared-key"),
    )
    replay = writer.registra(
        carico(raccolta=raccolta.raccolta_id.value, key="shared-key"),
    )
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert replay.movimento_id == first.movimento_id
    assert replay.stock_disponibile == first.stock_disponibile


def test_rejects_idempotency_key_reused_with_different_payload(seeded_raccolta):
    engine, raccolta = seeded_raccolta
    writer = PostgreSQLMovimentoCaricoWriter(_Factory(engine))
    writer.registra(carico(raccolta=raccolta.raccolta_id.value, key="conflict-key"))
    with pytest.raises(MovimentoCaricoIdempotencyConflictError):
        writer.registra(
            carico(raccolta=raccolta.raccolta_id.value, key="conflict-key", quantita="999"),
        )


def test_rejects_unknown_raccolta(seeded_raccolta):
    engine, _ = seeded_raccolta
    writer = PostgreSQLMovimentoCaricoWriter(_Factory(engine))
    with pytest.raises(MovimentoCaricoRaccoltaNotFoundError):
        writer.registra(carico(raccolta="RAC-999999"))


def test_rejects_stock_existing_with_non_gram_unit(seeded_raccolta):
    engine, raccolta = seeded_raccolta
    with engine.begin() as connection:
        varieta_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.varieta WHERE public_id='VAR-000001'"
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at,version) "
            "VALUES (%s,0,'SET',CURRENT_TIMESTAMP,0)",
            (varieta_pk,),
        )
    writer = PostgreSQLMovimentoCaricoWriter(_Factory(engine))
    with pytest.raises(MovimentoCaricoStockUnitMismatchError):
        writer.registra(carico(raccolta=raccolta.raccolta_id.value))
