"""Provenienza dichiarata per riga (campo ``semina``): il writer consuma
esattamente i lotti della SEMINA indicata o rifiuta la consegna."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from src.tpo_core.application.delivery_fulfilment.errors import (
    DeliveryValidationError,
    InvalidDeliveryCommandError,
)
from src.tpo_core.application.delivery_fulfilment.models import DeliveryFulfilmentCommand
from src.tpo_core.domain.identifiers import MovimentoId, SeminaId
from tests.infrastructure.postgresql.test_bolla_lettura_reader import _seed_carico_da_raccolta
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    TZ, _command, _consumi_per_scarico, _facts, _seed, _writer,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)


def _declared(command: DeliveryFulfilmentCommand, semina: str | None) -> DeliveryFulfilmentCommand:
    line = replace(
        command.lines[0], origin_semina=None if semina is None else SeminaId(semina)
    )
    return replace(command, lines=(line,))


def _second_lot(engine, number: int, quantity: str, codice: str, when: datetime) -> None:
    """Seconda semina/raccolta/carico per la STESSA varieta' (ids distinti)."""
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        variety_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.varieta WHERE public_id=%s", (f"VAR-{number:06d}",),
        ).scalar_one()
        semina_pk = connection.exec_driver_sql("""
          INSERT INTO tpo.semine
            (public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,
             protocollo_versione_id,stato,quantita_seme,unita_misura,data_avvio,
             causa_origine,cultivar_snapshot,uso_produttivo_snapshot,
             lotto_seme_snapshot,protocollo_snapshot,created_by,codice_tracciabilita)
          VALUES (%s,%s,1,1,1,1,'AVVIATA',10,'GRAM',%s,'PIANO_PRODUZIONE',
                  'x','x','x','x','decl-test',%s) RETURNING id
        """, (f"SEM-{number + 500:06d}", variety_pk, when, codice)).scalar_one()
        raccolta_pk = connection.exec_driver_sql("""
          INSERT INTO tpo.raccolte
            (public_id,semina_id,data_raccolta,quantita,unita_misura,created_by)
          VALUES (%s,%s,%s,%s,'SET','decl-test') RETURNING id
        """, (f"RAC-{number + 500:06d}", semina_pk, when, quantity)).scalar_one()
        connection.exec_driver_sql("""
          INSERT INTO tpo.movimenti_magazzino
            (public_id,varieta_id,unita_misura,tipo,direzione,quantita,data_movimento,
             motivo,origine_tipo,raccolta_id,created_at,created_by)
          VALUES (%s,%s,'SET','CARICO','POSITIVO',%s,%s,'carico da raccolta','RACCOLTA',
                  %s,%s,'decl-test')
        """, (f"MOV-{number + 600:06d}", variety_pk, quantity, when, raccolta_pk, when))


def test_declared_semina_overrides_fifo(writer_postgresql_engine) -> None:
    """Due lotti: il piu' vecchio (FIFO) e' SEM-<n>, ma l'operatore dichiara il
    piu' recente. Il consumo deve andare sul lotto dichiarato, non sul FIFO."""
    engine = writer_postgresql_engine
    _seed(engine, 940001, stock="3", order_quantity="3")
    _seed_carico_da_raccolta(engine, 940001, "2", "OLD-0110-A", datetime(2099, 1, 1, 8, tzinfo=TZ))
    _second_lot(engine, 940001, "1", "NEW-0210-A", datetime(2099, 1, 2, 8, tzinfo=TZ))
    command = _declared(_command(940001, "1", movement=940001), "SEM-940501")
    _writer(engine).publish(command)
    assert _consumi_per_scarico(engine, "MOV-940001") == [("MOV-940601", Decimal("1"))]


def test_declared_semina_without_declaration_still_uses_fifo(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 940002, stock="3", order_quantity="3")
    _seed_carico_da_raccolta(engine, 940002, "2", "OLD-0110-A", datetime(2099, 1, 1, 8, tzinfo=TZ))
    _second_lot(engine, 940002, "1", "NEW-0210-A", datetime(2099, 1, 2, 8, tzinfo=TZ))
    _writer(engine).publish(_command(940002, "1", movement=940002))
    assert _consumi_per_scarico(engine, "MOV-940002") == [("MOV-940102", Decimal("1"))]


def test_declared_semina_with_insufficient_stock_rejects_everything(writer_postgresql_engine) -> None:
    """Il lotto dichiarato ha 1 SET ma ne servono 2: nessun fallback silenzioso
    su un altro codice, la consegna intera viene rifiutata e nulla cambia."""
    engine = writer_postgresql_engine
    _seed(engine, 940003, stock="3", order_quantity="3")
    _seed_carico_da_raccolta(engine, 940003, "2", "OLD-0110-A", datetime(2099, 1, 1, 8, tzinfo=TZ))
    _second_lot(engine, 940003, "1", "NEW-0210-A", datetime(2099, 1, 2, 8, tzinfo=TZ))
    before = _facts(engine, 940003)
    command = _declared(_command(940003, "2", movement=940003), "SEM-940503")
    with pytest.raises(DeliveryValidationError, match="SEM-940503"):
        _writer(engine).publish(command)
    assert _facts(engine, 940003) == before
    assert _consumi_per_scarico(engine, "MOV-940003") == []


def test_declared_semina_unknown_or_other_variety_is_rejected(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _seed(engine, 940004, stock="2", order_quantity="2")
    _seed(engine, 940005, stock="2", order_quantity="2")
    _seed_carico_da_raccolta(engine, 940005, "2", "OTH-0110-A", datetime(2099, 1, 1, 8, tzinfo=TZ))
    with pytest.raises(DeliveryValidationError, match="inesistente"):
        _writer(engine).publish(_declared(_command(940004, "1", movement=940004), "SEM-999999"))
    with pytest.raises(DeliveryValidationError, match="altra VARIETA"):
        _writer(engine).publish(_declared(_command(940004, "1", movement=940004), "SEM-940005"))


def test_declared_semina_is_consumed_across_its_own_lots_and_exhausts(writer_postgresql_engine) -> None:
    """Dopo aver consegnato tutto il lotto dichiarato, una seconda consegna
    sulla stessa semina viene rifiutata (niente doppio consumo)."""
    engine = writer_postgresql_engine
    _seed(engine, 940006, stock="2", order_quantity="2")
    _seed_carico_da_raccolta(engine, 940006, "2", "ONE-0110-A", datetime(2099, 1, 1, 8, tzinfo=TZ))
    writer = _writer(engine)
    writer.publish(_declared(_command(940006, "1", movement=940006), "SEM-940006"))
    writer.publish(_declared(
        _command(940007, "1", order_version=1, line_version=1, movement=940007,
                 line_number=940006, client_number=940006), "SEM-940006"))
    assert _consumi_per_scarico(engine, "MOV-940007") == [("MOV-940106", Decimal("1"))]
    with pytest.raises(DeliveryValidationError):
        writer.publish(_declared(
            _command(940008, "1", order_version=2, line_version=2, movement=940008,
                     line_number=940006, client_number=940006), "SEM-940006"))


def test_correction_line_cannot_declare_a_semina() -> None:
    from src.tpo_core.application.delivery_fulfilment.models import (
        DeliveryFulfilmentLine, DeliveryLineReference,
    )
    from src.tpo_core.domain.identifiers import ConsegnaId, OrdineId
    from src.tpo_core.domain.quantities import UnitOfMeasure
    with pytest.raises(InvalidDeliveryCommandError):
        DeliveryFulfilmentLine(
            OrdineId("ORD-000001"), "RO-000001", Decimal("-1"), UnitOfMeasure.SET, 0, 0,
            None, DeliveryLineReference(ConsegnaId("CON-000001"), 1),
            origin_semina=SeminaId("SEM-000001"),
        )
