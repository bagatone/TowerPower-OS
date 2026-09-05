from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.movimento_articolo.errors import (
    MovimentoArticoloArticoloNotFoundError,
    MovimentoArticoloIdempotencyConflictError,
    MovimentoArticoloInsufficientStockError,
    MovimentoArticoloStockUnitMismatchError,
)
from src.tpo_core.application.movimento_articolo.models import (
    MovimentoArticoloAuthority, RegistraMovimentoArticolo,
)
from src.tpo_core.domain.identifiers import ActorId, ArticoloId
from src.tpo_core.domain.states import MovimentoDirection, MovimentoType
from src.tpo_core.infrastructure.postgresql.articolo import PostgreSQLArticoloWriter
from src.tpo_core.infrastructure.postgresql.movimento_articolo import (
    PostgreSQLMovimentoArticoloWriter,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)
from tests.integration.postgresql.test_articolo import articolo_environment, commission

BASE = datetime(2026, 9, 5, 8, tzinfo=timezone.utc)


def movimento(*, articolo="ART-000001", tipo=MovimentoType.CARICO, quantita="25.5",
              unita_misura="GRAM", key="mov-1", direzione=None, at=BASE,
              motivo="rifornimento substrato"):
    return RegistraMovimentoArticolo(
        articolo_id=ArticoloId(articolo),
        tipo=tipo,
        quantita=Decimal(quantita),
        unita_misura=unita_misura,
        effective_at=at,
        motivo=motivo,
        authority=MovimentoArticoloAuthority(
            ActorId("magazziniere"), "rifornimento", f"corr-{key}", key,
        ),
        direzione=direzione,
    )


@pytest.fixture
def seeded_articolo(articolo_environment):
    engine = articolo_environment
    writer = PostgreSQLArticoloWriter(_Factory(engine))
    result = writer.commission(commission())
    return engine, result


def test_carico_creates_movimento_and_increases_stock_articoli(seeded_articolo):
    engine, articolo = seeded_articolo
    writer = PostgreSQLMovimentoArticoloWriter(_Factory(engine))
    result = writer.registra(movimento(articolo=articolo.articolo_id.value))
    assert result.outcome == "INSERTED"
    assert result.stock_disponibile == Decimal("25.5")
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT tipo,direzione,quantita,unita_misura,origine_tipo,varieta_id,articolo_id "
            "FROM tpo.movimenti_magazzino WHERE public_id=%s",
            (result.movimento_id.value,),
        ).fetchone()
        assert row[0] == "CARICO"
        assert row[1] == "POSITIVO"
        assert Decimal(row[2]) == Decimal("25.5")
        assert row[3] == "GRAM"
        assert row[4] == "ARTICOLO_MOVIMENTO"
        assert row[5] is None
        assert row[6] is not None
        stock_row = connection.exec_driver_sql(
            "SELECT disponibile,unita_misura FROM tpo.stock_articoli WHERE articolo_id="
            "(SELECT id FROM tpo.articoli WHERE public_id=%s)",
            (articolo.articolo_id.value,),
        ).fetchone()
        assert stock_row[0] == Decimal("25.5")
        assert stock_row[1] == "GRAM"


def test_scarico_decreases_stock_articoli(seeded_articolo):
    engine, articolo = seeded_articolo
    writer = PostgreSQLMovimentoArticoloWriter(_Factory(engine))
    writer.registra(movimento(articolo=articolo.articolo_id.value, quantita="100", key="c1"))
    result = writer.registra(
        movimento(articolo=articolo.articolo_id.value, tipo=MovimentoType.SCARICO,
                  quantita="30", key="s1"),
    )
    assert result.stock_disponibile == Decimal("70")


def test_scarico_beyond_available_is_rejected(seeded_articolo):
    engine, articolo = seeded_articolo
    writer = PostgreSQLMovimentoArticoloWriter(_Factory(engine))
    writer.registra(movimento(articolo=articolo.articolo_id.value, quantita="10", key="c1"))
    with pytest.raises(MovimentoArticoloInsufficientStockError):
        writer.registra(
            movimento(articolo=articolo.articolo_id.value, tipo=MovimentoType.SCARICO,
                      quantita="20", key="s1"),
        )


def test_rettifica_negativa_reduces_stock(seeded_articolo):
    engine, articolo = seeded_articolo
    writer = PostgreSQLMovimentoArticoloWriter(_Factory(engine))
    writer.registra(movimento(articolo=articolo.articolo_id.value, quantita="50", key="c1"))
    result = writer.registra(
        movimento(articolo=articolo.articolo_id.value, tipo=MovimentoType.RETTIFICA,
                  quantita="5", direzione=MovimentoDirection.NEGATIVO, key="r1"),
    )
    assert result.stock_disponibile == Decimal("45")


def test_idempotent_replay_returns_same_movimento_without_double_counting(seeded_articolo):
    engine, articolo = seeded_articolo
    writer = PostgreSQLMovimentoArticoloWriter(_Factory(engine))
    first = writer.registra(movimento(articolo=articolo.articolo_id.value, key="shared-key"))
    replay = writer.registra(movimento(articolo=articolo.articolo_id.value, key="shared-key"))
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert replay.movimento_id == first.movimento_id
    assert replay.stock_disponibile == first.stock_disponibile


def test_rejects_idempotency_key_reused_with_different_payload(seeded_articolo):
    engine, articolo = seeded_articolo
    writer = PostgreSQLMovimentoArticoloWriter(_Factory(engine))
    writer.registra(movimento(articolo=articolo.articolo_id.value, key="conflict-key"))
    with pytest.raises(MovimentoArticoloIdempotencyConflictError):
        writer.registra(
            movimento(articolo=articolo.articolo_id.value, key="conflict-key", quantita="999"),
        )


def test_rejects_unknown_articolo(seeded_articolo):
    engine, _ = seeded_articolo
    writer = PostgreSQLMovimentoArticoloWriter(_Factory(engine))
    with pytest.raises(MovimentoArticoloArticoloNotFoundError):
        writer.registra(movimento(articolo="ART-999999"))


def test_rejects_stock_existing_with_mismatched_unit(seeded_articolo):
    engine, articolo = seeded_articolo
    with engine.begin() as connection:
        articolo_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.articoli WHERE public_id=%s", (articolo.articolo_id.value,),
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO tpo.stock_articoli(articolo_id,disponibile,unita_misura,"
            "updated_at,version) VALUES (%s,0,'UNIT',CURRENT_TIMESTAMP,0)",
            (articolo_pk,),
        )
    writer = PostgreSQLMovimentoArticoloWriter(_Factory(engine))
    with pytest.raises(MovimentoArticoloStockUnitMismatchError):
        writer.registra(movimento(articolo=articolo.articolo_id.value))
