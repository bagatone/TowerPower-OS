"""Ordine manuale: registrazione governata e consegna successiva con codice di
tracciabilita' dichiarato."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import pytest

from src.tpo_core.application.delivery_fulfilment.models import (
    DeliveryFulfilmentCommand, DeliveryFulfilmentLine,
)
from src.tpo_core.application.ordine_manuale import (
    InvalidOrdineManualeCommandError,
    OrdineManualeAuthority,
    OrdineManualeClienteNotFoundError,
    OrdineManualeIdempotencyConflictError,
    OrdineManualeVarietaError,
    RegistraOrdineManuale,
    RigaOrdineManuale,
)
from src.tpo_core.domain.identifiers import (
    ActorId, ClienteId, ConsegnaId, MovimentoId, OrdineId, SeminaId, VarietaId,
)
from src.tpo_core.domain.quantities import UnitOfMeasure
from src.tpo_core.infrastructure.postgresql.ordine_manuale import PostgreSQLOrdineManualeWriter
from tests.infrastructure.postgresql.test_bolla_lettura_reader import _seed_carico_da_raccolta
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    NOW, TZ, _consumi_per_scarico, _Factory, _seed, _writer,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)


def _client_and_variety(engine, number: int, *, state: str = "ATTIVA") -> None:
    with engine.begin() as connection:
        # la sequenza RIGA_ORDINE_ID esiste nel database reale (planning commit);
        # nel database di test migrato viene creata qui, lontano dagli id dei seed.
        connection.exec_driver_sql("""
          INSERT INTO tpo.id_sequences
            (sequence_name,identifier_type,prefix,next_value,version,updated_at,updated_by)
          VALUES ('RIGA_ORDINE_ID','RigaOrdineId','RO',970000,0,now(),'om-test')
          ON CONFLICT (sequence_name) DO NOTHING
        """)
        connection.exec_driver_sql("""
          INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
          VALUES (%s,%s,'om-test',%s,'om-test')
        """, (f"CLI-{number:06d}", f"OM client {number}", NOW))
        connection.exec_driver_sql("""
          INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,updated_at,updated_by)
          VALUES (%s,%s,%s,'om-test',%s,'om-test')
        """, (f"VAR-{number:06d}", f"OM variety {number}", state, NOW))


def _command(number: int, quantity: str = "1", *, key: str | None = None,
             client: int | None = None) -> RegistraOrdineManuale:
    return RegistraOrdineManuale(
        ClienteId(f"CLI-{(client or number):06d}"), date(2099, 1, 3), date(2099, 1, 5),
        (RigaOrdineManuale(VarietaId(f"VAR-{number:06d}"), Decimal(quantity), UnitOfMeasure.SET),),
        OrdineManualeAuthority(ActorId("om-test"), "ordine extra", f"om-{number}",
                               key or f"om-key-{number}-{quantity}"),
    )


def _owriter(engine) -> PostgreSQLOrdineManualeWriter:
    return PostgreSQLOrdineManualeWriter(_Factory(engine))


def test_ordine_manuale_is_registered_with_identities_audit_and_idempotency(
        writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _client_and_variety(engine, 960001)
    result = _owriter(engine).registra(_command(960001, "2"))
    assert result.outcome == "INSERTED" and result.stato == "APERTO" and result.version == 0
    assert result.ordine_id.value.startswith("ORD-")
    assert [r.riga_id.value[:3] for r in result.righe] == ["RO-"]
    with engine.connect() as connection:
        row = connection.exec_driver_sql("""
          SELECT o.tipo_creazione::text, o.stato::text, o.run_id, o.programma_fornitura_id,
                 o.chiave_idempotenza, ro.quantita, ro.unita_misura::text
          FROM tpo.ordini o JOIN tpo.righe_ordine ro ON ro.ordine_id=o.id
          WHERE o.public_id=%s""", (result.ordine_id.value,)).one()
        audit = connection.exec_driver_sql("""
          SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='ORDINE'
            AND entity_public_id=%s AND correlation_id='om-960001'
        """, (result.ordine_id.value,)).scalar_one()
    assert row == ("MANUALE", "APERTO", None, None, None, Decimal("2"), "SET")
    assert audit == 1
    replay = _owriter(engine).registra(_command(960001, "2"))
    assert replay.outcome == "COMPATIBLE_REPLAY" and replay.ordine_id == result.ordine_id
    assert replay.righe == result.righe
    with pytest.raises(OrdineManualeIdempotencyConflictError):
        _owriter(engine).registra(_command(960001, "3", key="om-key-960001-2"))


def test_ordine_manuale_rejects_unknown_client_and_inactive_variety(writer_postgresql_engine) -> None:
    engine = writer_postgresql_engine
    _client_and_variety(engine, 960002, state="SOSPESA")
    with pytest.raises(OrdineManualeVarietaError, match="SOSPESA"):
        _owriter(engine).registra(_command(960002))
    with pytest.raises(OrdineManualeClienteNotFoundError):
        _owriter(engine).registra(_command(960002, client=969999, key="other"))


def test_ordine_manuale_then_declared_delivery_writes_the_code_on_the_bolla(
        writer_postgresql_engine) -> None:
    """Percorso reale: ordine manuale -> consegna con semina dichiarata."""
    engine = writer_postgresql_engine
    _client_and_variety(engine, 960003)
    with engine.begin() as connection:
        variety_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.varieta WHERE public_id='VAR-960003'").scalar_one()
        connection.exec_driver_sql("""
          INSERT INTO tpo.stock(varieta_id,disponibile,unita_misura,updated_at)
          VALUES (%s,1,'SET',%s)""", (variety_pk, NOW))
    _seed_carico_da_raccolta(engine, 960003, "1", "MAN-0310-A", datetime(2099, 1, 2, 8, tzinfo=TZ))
    ordine = _owriter(engine).registra(_command(960003))
    riga = ordine.righe[0]
    command = DeliveryFulfilmentCommand(
        ConsegnaId("CON-960003"), ClienteId("CLI-960003"), date(2099, 1, 5), NOW,
        (DeliveryFulfilmentLine(
            ordine.ordine_id, riga.riga_id.value, Decimal("1"), UnitOfMeasure.SET,
            ordine.version, 0, MovimentoId("MOV-960003"), None, SeminaId("SEM-960003"),
        ),),
        ActorId("om-test"), "consegna di test", "om-delivery-960003",
    )
    result = _writer(engine).publish(command)
    assert result.order_states == ((ordine.ordine_id, "EVASO"),)
    assert _consumi_per_scarico(engine, "MOV-960003") == [("MOV-960103", Decimal("1"))]


def test_ordine_manuale_command_validation() -> None:
    with pytest.raises(InvalidOrdineManualeCommandError):
        replace(_command(1), righe=())
    with pytest.raises(InvalidOrdineManualeCommandError):
        replace(_command(1), data_consegna_prevista=date(2098, 1, 1))
    riga = _command(1).righe[0]
    with pytest.raises(InvalidOrdineManualeCommandError):
        replace(_command(1), righe=(riga, riga))
    with pytest.raises(InvalidOrdineManualeCommandError):
        RigaOrdineManuale(VarietaId("VAR-000001"), Decimal("0"), UnitOfMeasure.SET)
    with pytest.raises(InvalidOrdineManualeCommandError):
        RigaOrdineManuale(VarietaId("VAR-000001"), Decimal("1"), UnitOfMeasure.UNIT)
