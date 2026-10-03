"""Rettifica di giacenza: la merce che non esiste piu' esce dallo STOCK e dai
lotti con un nuovo MOVIMENTO tracciato, senza toccare lo storico."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from src.tpo_core.application.rettifica_giacenza import (
    InvalidRettificaGiacenzaCommandError,
    RettificaGiacenza,
    RettificaGiacenzaAuthority,
    RettificaGiacenzaIdempotencyConflictError,
    RettificaGiacenzaOrigineError,
    RettificaGiacenzaStockError,
    RettificaGiacenzaVarietaNotFoundError,
)
from src.tpo_core.application.delivery_fulfilment.errors import DeliveryValidationError
from src.tpo_core.domain.identifiers import ActorId, SeminaId, VarietaId
from src.tpo_core.domain.quantities import UnitOfMeasure
from src.tpo_core.infrastructure.postgresql.rettifica_giacenza import (
    PostgreSQLRettificaGiacenzaWriter,
)
from tests.infrastructure.postgresql.test_bolla_lettura_reader import _seed_carico_da_raccolta
from tests.infrastructure.postgresql.test_delivery_declared_semina import _declared, _second_lot
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    NOW, TZ, _command, _Factory, _seed, _writer,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)


def _rettifica(number: int, quantity: str, *, key: str | None = None,
               semina: int | None = None, motivo: str = "vendita non registrata") -> RettificaGiacenza:
    return RettificaGiacenza(
        VarietaId(f"VAR-{number:06d}"), UnitOfMeasure.SET, Decimal(quantity),
        datetime(2099, 1, 3, 8, tzinfo=TZ), motivo,
        RettificaGiacenzaAuthority(
            ActorId("writer-test"), "rettifica di test", f"rett-{number}",
            key or f"rett-key-{number}-{quantity}",
        ),
        None if semina is None else SeminaId(f"SEM-{semina:06d}"),
    )


def _rwriter(engine) -> PostgreSQLRettificaGiacenzaWriter:
    return PostgreSQLRettificaGiacenzaWriter(_Factory(engine))


def _stock(engine, number: int) -> Decimal:
    with engine.connect() as connection:
        return Decimal(connection.exec_driver_sql("""
          SELECT s.disponibile FROM tpo.stock s JOIN tpo.varieta v ON v.id=s.varieta_id
          WHERE v.public_id=%s AND s.unita_misura='SET'
        """, (f"VAR-{number:06d}",)).scalar_one())


def _consumi_rettifica(engine, movimento: str) -> list[tuple[str, str, Decimal]]:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("""
          SELECT mc.public_id, cl.tipo_consumo::text, cl.quantita FROM tpo.consumi_lotto cl
          JOIN tpo.movimenti_magazzino mc ON mc.id = cl.movimento_carico_id
          JOIN tpo.movimenti_magazzino ms ON ms.id = cl.movimento_scarico_id
          WHERE ms.public_id = %s ORDER BY mc.public_id
        """, (movimento,)).all()
        return [(r[0], r[1], r[2]) for r in rows]


def test_rettifica_removes_stock_and_consumes_oldest_lot(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 950001, stock="3", order_quantity="3")
    _seed_carico_da_raccolta(engine, 950001, "2", "OLD-0110-A", datetime(2099, 1, 1, 8, tzinfo=TZ))
    _second_lot(engine, 950001, "1", "NEW-0210-A", datetime(2099, 1, 2, 8, tzinfo=TZ))
    result = _rwriter(engine).registra(_rettifica(950001, "2"))
    assert result.outcome == "INSERTED" and result.stock_disponibile == Decimal("1")
    assert _stock(engine, 950001) == Decimal("1")
    assert _consumi_rettifica(engine, result.movimento_id.value) == [
        ("MOV-950101", "RETTIFICA_GIACENZA", Decimal("2")),
    ]
    with engine.connect() as connection:
        movimento = connection.exec_driver_sql("""
          SELECT tipo::text, direzione::text, origine_tipo, motivo FROM tpo.movimenti_magazzino
          WHERE public_id=%s""", (result.movimento_id.value,)).one()
        audit = connection.exec_driver_sql("""
          SELECT count(*) FROM tpo.audit_eventi WHERE entity_public_id=%s
            AND correlation_id='rett-950001'""", (result.movimento_id.value,)).scalar_one()
    assert movimento == ("SCARICO", "NEGATIVO", "RETTIFICA_GIACENZA", "vendita non registrata")
    assert audit == 1


def test_rettifica_with_declared_semina_and_following_delivery_does_not_reuse_removed_lot(
        writer_postgresql_engine) -> None:
    """La merce rettificata non puo' piu' comparire su una bolla: dopo aver
    rimosso il lotto vecchio, la consegna FIFO usa il lotto nuovo."""
    engine = writer_postgresql_engine
    _seed(engine, 950002, stock="3", order_quantity="3")
    _seed_carico_da_raccolta(engine, 950002, "2", "OLD-0110-A", datetime(2099, 1, 1, 8, tzinfo=TZ))
    _second_lot(engine, 950002, "1", "NEW-0210-A", datetime(2099, 1, 2, 8, tzinfo=TZ))
    _rwriter(engine).registra(_rettifica(950002, "2", semina=950002))
    _writer(engine).publish(_command(950002, "1", movement=950002))
    from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import _consumi_per_scarico
    assert _consumi_per_scarico(engine, "MOV-950002") == [("MOV-950602", Decimal("1"))]
    # il lotto vecchio, rettificato per intero, non e' piu' dichiarabile
    with pytest.raises(DeliveryValidationError):
        _writer(engine).publish(_declared(_command(
            950003, "1", order_version=1, line_version=1, movement=950003,
            line_number=950002, client_number=950002), "SEM-950002"))


def test_rettifica_declared_semina_must_be_honourable(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 950004, stock="3", order_quantity="3")
    _seed_carico_da_raccolta(engine, 950004, "1", "ONE-0110-A", datetime(2099, 1, 1, 8, tzinfo=TZ))
    before = _stock(engine, 950004)
    with pytest.raises(RettificaGiacenzaOrigineError, match="SEM-950004"):
        _rwriter(engine).registra(_rettifica(950004, "2", semina=950004))
    assert _stock(engine, 950004) == before


def test_rettifica_untraced_stock_is_removed_without_attributing_a_code(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    # giacenza 3 = 2 senza origine + 1 da lotto: rimuovere 2 non tocca il lotto
    _seed(engine, 950005, stock="3", order_quantity="3")
    _seed_carico_da_raccolta(engine, 950005, "1", "ONE-0110-A", datetime(2099, 1, 1, 8, tzinfo=TZ))
    result = _rwriter(engine).registra(_rettifica(950005, "2"))
    assert _consumi_rettifica(engine, result.movimento_id.value) == []
    assert _stock(engine, 950005) == Decimal("1")


def test_rettifica_insufficient_stock_and_unknown_variety_are_rejected(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 950006, stock="1", order_quantity="1")
    with pytest.raises(RettificaGiacenzaStockError):
        _rwriter(engine).registra(_rettifica(950006, "2"))
    assert _stock(engine, 950006) == Decimal("1")
    with pytest.raises(RettificaGiacenzaVarietaNotFoundError):
        _rwriter(engine).registra(_rettifica(959999, "1"))


def test_rettifica_is_idempotent_and_conflicts_on_changed_payload(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 950007, stock="3", order_quantity="3")
    first = _rwriter(engine).registra(_rettifica(950007, "1", key="same-key"))
    replay = _rwriter(engine).registra(_rettifica(950007, "1", key="same-key"))
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert replay.movimento_id == first.movimento_id
    assert _stock(engine, 950007) == Decimal("2")
    with pytest.raises(RettificaGiacenzaIdempotencyConflictError):
        _rwriter(engine).registra(_rettifica(950007, "2", key="same-key"))
    assert _stock(engine, 950007) == Decimal("2")


def test_rettifica_command_validation() -> None:
    with pytest.raises(InvalidRettificaGiacenzaCommandError):
        _rettifica(1, "0")
    with pytest.raises(InvalidRettificaGiacenzaCommandError):
        _rettifica(1, "-1")
    with pytest.raises(InvalidRettificaGiacenzaCommandError):
        _rettifica(1, "1", motivo=" ")
