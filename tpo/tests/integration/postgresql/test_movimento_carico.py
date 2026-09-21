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
from src.tpo_core.domain.quantities import UnitOfMeasure
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


def carico(*, raccolta="RAC-000001", unita_misura=UnitOfMeasure.GRAM, quantita="450.5",
           key="carico-1", at=BASE, motivo="pesatura carico"):
    return RegistraCaricoMagazzino(
        raccolta_id=RaccoltaId(raccolta),
        unita_misura=unita_misura,
        quantita_pesata=(Decimal(quantita) if unita_misura is UnitOfMeasure.GRAM else None),
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
    # da nessuno stock esistente o da uno stock gia' in GRAM o SET a seconda
    # del percorso testato (Owner Decision D11/D13): la ripuliamo qui per
    # isolare i test CARICO da quel fixture legacy.
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
    # Nota (20/9/2026, dopo il redesign a chiave composita del Fatto 25): il
    # guardrail blocca ora solo un'unita' diversa VIVA (disponibile>0), non
    # una riga storica congelata a 0 (che invece deve poter coesistere senza
    # bloccare un nuovo CARICO) — quindi la riga di test deve essere viva
    # per verificare davvero questo guardrail.
    engine, raccolta = seeded_raccolta
    with engine.begin() as connection:
        varieta_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.varieta WHERE public_id='VAR-000001'"
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at,version) "
            "VALUES (%s,5,'SET',CURRENT_TIMESTAMP,0)",
            (varieta_pk,),
        )
    writer = PostgreSQLMovimentoCaricoWriter(_Factory(engine))
    with pytest.raises(MovimentoCaricoStockUnitMismatchError):
        writer.registra(carico(raccolta=raccolta.raccolta_id.value))


def test_set_carico_takes_quantity_from_raccolta_own_set_quantity(seeded_raccolta):
    engine, raccolta = seeded_raccolta
    writer = PostgreSQLMovimentoCaricoWriter(_Factory(engine))
    result = writer.registra(
        carico(raccolta=raccolta.raccolta_id.value, unita_misura=UnitOfMeasure.SET, key="set-1"),
    )
    assert result.outcome == "INSERTED"
    assert result.unita_misura is UnitOfMeasure.SET
    # harvest() di default registra 0.5 SET (tests/integration/postgresql/test_raccolta.py);
    # la quantita' del CARICO deve coincidere esattamente, mai dichiarata di nuovo (D14).
    assert result.quantita == Decimal("0.5")
    assert result.stock_disponibile == Decimal("0.5")
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT quantita,unita_misura FROM tpo.movimenti_magazzino WHERE public_id=%s",
            (result.movimento_id.value,),
        ).fetchone()
        assert Decimal(row[0]) == Decimal("0.5")
        assert row[1] == "SET"
        stock_row = connection.exec_driver_sql(
            "SELECT disponibile,unita_misura FROM tpo.stock WHERE varieta_id="
            "(SELECT id FROM tpo.varieta WHERE public_id='VAR-000001')"
        ).fetchone()
        assert stock_row[0] == Decimal("0.5")
        assert stock_row[1] == "SET"


def test_multiple_partial_set_carichi_accumulate_stock(seeded_raccolta):
    engine, raccolta = seeded_raccolta
    writer = PostgreSQLMovimentoCaricoWriter(_Factory(engine))
    first = writer.registra(
        carico(raccolta=raccolta.raccolta_id.value, unita_misura=UnitOfMeasure.SET, key="set-k1"),
    )
    second = writer.registra(
        carico(raccolta=raccolta.raccolta_id.value, unita_misura=UnitOfMeasure.SET, key="set-k2"),
    )
    assert first.movimento_id != second.movimento_id
    assert second.stock_disponibile == Decimal("1.0")


def test_rejects_set_carico_when_stock_already_in_gram(seeded_raccolta):
    # Stessa nota di test_rejects_stock_existing_with_non_gram_unit sopra:
    # serve una riga GRAM viva (disponibile>0) per esercitare davvero il
    # guardrail post-Fatto 25.
    engine, raccolta = seeded_raccolta
    with engine.begin() as connection:
        varieta_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.varieta WHERE public_id='VAR-000001'"
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at,version) "
            "VALUES (%s,5,'GRAM',CURRENT_TIMESTAMP,0)",
            (varieta_pk,),
        )
    writer = PostgreSQLMovimentoCaricoWriter(_Factory(engine))
    with pytest.raises(MovimentoCaricoStockUnitMismatchError):
        writer.registra(
            carico(raccolta=raccolta.raccolta_id.value, unita_misura=UnitOfMeasure.SET),
        )


def test_frozen_stock_row_in_other_unit_does_not_block_carico(seeded_raccolta):
    # Copre direttamente la policy introdotta dal Fatto 25 (chiave composita
    # tpo.stock): una riga storica congelata (disponibile=0) in un'altra
    # unita' di misura NON deve piu' bloccare un nuovo CARICO, a differenza
    # di una riga viva (vedi i due test sopra). Riproduce lo scenario reale
    # Afila/Cilantro: riga GRAM residua a 0 dopo il congelamento, nuovo
    # CARICO in SET deve riuscire.
    engine, raccolta = seeded_raccolta
    with engine.begin() as connection:
        varieta_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.varieta WHERE public_id='VAR-000001'"
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at,version) "
            "VALUES (%s,0,'GRAM',CURRENT_TIMESTAMP,0)",
            (varieta_pk,),
        )
    writer = PostgreSQLMovimentoCaricoWriter(_Factory(engine))
    result = writer.registra(
        carico(raccolta=raccolta.raccolta_id.value, unita_misura=UnitOfMeasure.SET, key="frozen-ok"),
    )
    assert result.outcome == "INSERTED"
    assert result.unita_misura is UnitOfMeasure.SET
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT unita_misura,disponibile FROM tpo.stock WHERE varieta_id=%s ORDER BY unita_misura",
            (varieta_pk,),
        ).all()
    by_unit = {row[0]: row[1] for row in rows}
    assert by_unit["GRAM"] == Decimal("0")
    assert by_unit["SET"] > Decimal("0")


def test_set_idempotent_replay_returns_same_movimento(seeded_raccolta):
    engine, raccolta = seeded_raccolta
    writer = PostgreSQLMovimentoCaricoWriter(_Factory(engine))
    first = writer.registra(
        carico(raccolta=raccolta.raccolta_id.value, unita_misura=UnitOfMeasure.SET, key="set-shared"),
    )
    replay = writer.registra(
        carico(raccolta=raccolta.raccolta_id.value, unita_misura=UnitOfMeasure.SET, key="set-shared"),
    )
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert replay.movimento_id == first.movimento_id
    assert replay.unita_misura is UnitOfMeasure.SET
    assert replay.stock_disponibile == first.stock_disponibile
